from pathlib import Path
from tempfile import TemporaryDirectory

from git import Repo

from ..agent.core.git_pull import git_pull


def main() -> None:
    with TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        remote_path = workdir / "remote.git"
        source_path = workdir / "source"
        clone_path = workdir / "clone"

        remote = Repo.init(remote_path, bare=True)
        source_repo = Repo.init(source_path)
        (source_path / "README.md").write_text("hello\n", encoding="utf-8")
        source_repo.index.add(["README.md"])
        source_repo.index.commit("init")
        source_repo.create_remote("origin", remote_path.as_posix())
        source_repo.git.push("-u", "origin", "HEAD")

        clone_repo = Repo.clone_from(remote_path.as_posix(), clone_path)

        (source_path / "README.md").write_text("hello\nworld\n", encoding="utf-8")
        source_repo.index.add(["README.md"])
        source_repo.index.commit("update")
        source_repo.git.push()

        result = git_pull("clone", workdir=workdir)
        updated = (clone_path / "README.md").read_text(encoding="utf-8")

        assert "update" in result or "Fast-forward" in result or "Updating" in result, result
        assert updated == "hello\nworld\n", updated

        clone_repo.close()
        source_repo.close()
        remote.close()


if __name__ == "__main__":
    main()
    print("git_pull integration ok")
