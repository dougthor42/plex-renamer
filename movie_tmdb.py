"""
"""
import os
import re
from datetime import date
from pathlib import Path
from typing import List
from typing import Optional

import click
import tmdbsimple as tmdb
from loguru import logger

INVALID_FILENAME_CHARS = {"<", ">", ":", '"', "/", "\\", "|", "?", "*"}
VIDEO_EXT = {".avi", ".mp4", ".mkv", ".m4v", ".ogm"}
RE_GOOD_FN = re.compile(r"^.+ \(\d{4}\) \{t[mv]db-\d+\}$")

tmdb.API_KEY = (Path(__file__).parent / "API_KEY").read_text().strip()

tmdb.REQUEST_TIMEOUT = 10  # seconds


class SearchResult:
    def __init__(self, data):
        self.raw = data
        self.title = data["title"]
        self.id_ = data["id"]
        try:
            self.release = date.fromisoformat(data["release_date"])
        except ValueError:
            logger.warning(f"Can't get release date from {self.title} {self.id_}")
            self.release = date(1970, 1, 1)
        except KeyError:
            logger.warning(
                "Data does not have 'release_date'. It might be coming soon..."
            )
            self.release = date(1970, 1, 1)

    def __str__(self):
        return make_filename(self)


def make_filename(result: SearchResult):
    """
    Make a Plex-friendly filename from the SearchResult.

    See https://support.plex.tv/articles/naming-and-organizing-your-movie-media-files/
    """
    # Clean the title because some might have characters that can't be used
    # in a filename, like "Who?"
    clean_title = "".join(c for c in result.title if c not in INVALID_FILENAME_CHARS)

    # Special case: the clean title is now empty (there exists at least 1 movie
    # who's title is just "?": https://www.themoviedb.org/movie/918197
    if clean_title == "":
        clean_title = "FIXME"

    fn = f"{clean_title} ({result.release.year})"
    fn += " {tmdb-" + str(result.id_) + "}"

    return fn


def ask_user(
    results: List[SearchResult], original_file: str, confirm: bool = False
) -> SearchResult:
    """
    Prompt the user which result they want to use.

    If only a single result is found, and `confirm` is True, then ask the user
    to select that option anyway.
    """
    print("Found results:")
    for n, result in enumerate(results):
        print(f"{n+1: >3d}: {result}")

    err_msg = f"Value must be an integer between 0 and {len(results)}, inclusive."

    if len(results) == 1 and not confirm:
        selection = results[0]
        logger.info(f"Single result found: ({original_file}) -> ({selection})")
        return selection

    while True:
        val = input(f"Which should I use for '{original_file}'? 0 aborts. [1]: ")
        # Allow user to drop into pdb.
        if val.lower() == "b":
            breakpoint()

        try:
            if val == "":
                val = 1
            val = int(val)
        except ValueError:
            print(err_msg)
            continue

        if val == 0:
            raise RuntimeError("User aborted")
        elif val == "":
            # using default of 1 (index 0)
            selection = results[0]
        elif val < 0 or val > len(results):
            print(err_msg)
        else:
            selection = results[val - 1]
            break

    logger.info(f"User selected: {selection}")
    return selection


def search(query: str, original_file: str) -> Optional[List[SearchResult]]:
    search = tmdb.Search()
    search.movie(query=query)

    results = [SearchResult(r) for r in search.results]

    if len(results) == 0:
        logger.warning(f"0 results for '{query}'. Skipping.")
        return None

    return results


def _strip_year(data: str) -> str:
    """
    Remove any year patterns from the string.
    """
    # Matches eg: [1990], (2024)
    year_re = re.compile(
        r"""
        (
            \[\d{4}\]
            |
            \(\d{4}\)
        )
        """,
        re.VERBOSE,
    )

    result = year_re.sub("", data).strip()
    return result


def _strip_leading_info(data: str) -> str:
    """
    Remove any "leading" info. Only if data looks like "info - 00 - title"
    """

    patt = re.compile(
        r"""
        ^(.*? - )(.*-.*$)
        """,
        re.VERBOSE,
    )

    if (match := patt.fullmatch(data)) is not None:
        return match.group(2).strip()
    else:
        logger.debug("data does not look like 'info - 00 - title'")
        return data


def _strip_leading_number(data: str) -> str:
    """
    "01 - Foo" -> "Foo"
    """

    return data.lstrip("0123456789 -")


def _first_couple_words_from_dots(data: str) -> str:
    """
    Some.Long.Title.foo.bar.XXYYZZ.baz -> "Some Long"
    """
    split_by_dot = data.split(".")
    if len(split_by_dot) > 2:
        return " ".join(split_by_dot[:2])
    return data


def get_search_term_from_fn(fn: str) -> str:
    """
    Attempt to get a search term from the filename.

    The filename should **not** have the extension.
    """
    best_guess = fn

    best_guess = _strip_year(best_guess)
    best_guess = _strip_leading_info(best_guess)
    best_guess = _strip_leading_number(best_guess)
    best_guess = _first_couple_words_from_dots(best_guess)

    return best_guess


def create_new_filepath(fp: Path, result: SearchResult) -> Path:
    """
    Create the new filepath.

    Returns
    -------
    new_fp: pathlib.Path
        The full path to the new file name.
    """
    original_ext = fp.suffix

    new_fn = make_filename(result)
    new_fp = fp.with_name(new_fn + original_ext)
    logger.info(f"{fp.name}  -->  {new_fp.name}")
    return new_fp


def move_to_folder(fp: Path, dry_run: bool = False) -> Optional[Path]:
    """
    Move files to the correct folder path.
    """
    folder_name = fp.stem
    if fp.parent.name != folder_name:
        new_path = fp.parent / folder_name / fp.name
        logger.info(f"Moving {fp} to {new_path}")
        if not dry_run:
            new_path.parent.mkdir()
            fp.rename(new_path)
        return new_path


def loop_path(path: Path, confirm: bool = True, dry_run: bool = False) -> None:

    num_changed = 0
    num_files_moved = 0

    for root, _, files in os.walk(path):
        for file in sorted(files):
            fp = Path(root) / file

            # only deal with video files
            if fp.suffix.lower() not in VIDEO_EXT:
                logger.info(f"Skip '{fp}` - doesn't appear to be a video file.")
                continue

            logger.info(f"Checking '{fp}'")

            # Skip files that already match our pattern
            if RE_GOOD_FN.fullmatch(fp.stem) is not None:
                logger.info(f"Skip renaming '{fp.name}': already looks good!")
                new_folder = move_to_folder(fp, dry_run=dry_run)
                if new_folder is not None:
                    num_files_moved += 1
                continue

            query = get_search_term_from_fn(fp.stem)
            results = search(query, fp.name)
            if results is not None:
                selection = ask_user(results, file, confirm=confirm)
                new_fp = create_new_filepath(fp, selection)
                num_changed += 1
                logger.info(f"Renaming '{fp}' to '{new_fp}'")
                if not dry_run:
                    try:
                        fp.rename(new_fp)
                        move_to_folder(new_fp)
                    except PermissionError:
                        msg = (
                            f"Permission denied when trying to rename '{fp}'."
                            " Did you forget to run with 'sudo'?"
                        )
                        logger.error(msg)

    logger.info(f"Number of files changed: {num_changed}")
    logger.info(f"Number of files moved: {num_files_moved}")


@click.command()
@click.option("-n", "--dry-run", is_flag=True, help="Do not rename files.")
@click.option(
    "--confirm/--no-confirm",
    is_flag=True,
    help="Confirm each result, even those whose search only returned a single value.",
)
@click.argument("folder", type=click.Path(exists=True, file_okay=False, path_type=Path))
def main(folder, dry_run, confirm):
    if dry_run:
        logger.warning("DRY RUN: files will not be renamed.")

    loop_path(folder, confirm=confirm, dry_run=dry_run)


if __name__ == "__main__":
    main()
