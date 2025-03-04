import os
from contextlib import _GeneratorContextManager as GCM
from contextlib import contextmanager

from funcy import reraise

from dvc.exceptions import (
    NotDvcRepoError,
    OutputNotFoundError,
    PathMissingError,
)
from dvc.external_repo import external_repo
from dvc.path_info import PathInfo
from dvc.repo import Repo


def get_url(path, repo=None, rev=None, remote=None):
    """
    Returns the URL to the storage location of a data file or directory tracked
    in a DVC repo. For Git repos, HEAD is used unless a rev argument is
    supplied. The default remote is tried unless a remote argument is supplied.

    Raises OutputNotFoundError if the file is not a dvc-tracked file.

    NOTE: This function does not check for the actual existence of the file or
    directory in the remote storage.
    """
    with _make_repo(repo, rev=rev) as _repo:
        path_info = PathInfo(_repo.root_dir) / path
        with reraise(FileNotFoundError, PathMissingError(path, repo)):
            metadata = _repo.repo_tree.metadata(path_info)

        if not metadata.is_dvc:
            raise OutputNotFoundError(path, repo)

        cloud = metadata.repo.cloud
        hash_info = _repo.repo_tree.get_hash(path_info)
        return cloud.get_url_for(remote, checksum=hash_info.value)


def open(  # noqa, pylint: disable=redefined-builtin
    path, repo=None, rev=None, remote=None, mode="r", encoding=None
):
    """
    Open file in the supplied path tracked in a repo (both DVC projects and
    plain Git repos are supported). For Git repos, HEAD is used unless a rev
    argument is supplied. The default remote is tried unless a remote argument
    is supplied. It may only be used as a context manager:

        with dvc.api.open(
                'path/to/file',
                repo='https://example.com/url/to/repo'
                ) as fd:
            # ... Handle file object fd
    """
    args = (path,)
    kwargs = {
        "repo": repo,
        "remote": remote,
        "rev": rev,
        "mode": mode,
        "encoding": encoding,
    }
    return _OpenContextManager(_open, args, kwargs)


class _OpenContextManager(GCM):
    def __init__(
        self, func, args, kwds
    ):  # pylint: disable=super-init-not-called
        self.gen = func(*args, **kwds)
        self.func, self.args, self.kwds = func, args, kwds

    def __getattr__(self, name):
        raise AttributeError(
            "dvc.api.open() should be used in a with statement."
        )


def _open(path, repo=None, rev=None, remote=None, mode="r", encoding=None):
    with _make_repo(repo, rev=rev) as _repo:
        with _repo.open_by_relpath(
            path, remote=remote, mode=mode, encoding=encoding
        ) as fd:
            yield fd


def read(path, repo=None, rev=None, remote=None, mode="r", encoding=None):
    """
    Returns the contents of a tracked file (by DVC or Git). For Git repos, HEAD
    is used unless a rev argument is supplied. The default remote is tried
    unless a remote argument is supplied.
    """
    with open(
        path, repo=repo, rev=rev, remote=remote, mode=mode, encoding=encoding
    ) as fd:
        return fd.read()


@contextmanager
def _make_repo(repo_url=None, rev=None):
    repo_url = repo_url or os.getcwd()
    if rev is None and os.path.exists(repo_url):
        try:
            yield Repo(repo_url, subrepos=True)
            return
        except NotDvcRepoError:
            pass  # fallthrough to external_repo
    with external_repo(url=repo_url, rev=rev) as repo:
        yield repo
