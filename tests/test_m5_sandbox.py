"""M5 Sandbox Foundation security and resource-limit acceptance tests."""

import stat
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest
from eea_adapters.sandbox import SafeArchiveMaterializer, StructuredCommandExecutor
from eea_core.enums import EngineeringErrorCode
from eea_core.errors import EngineeringError
from eea_core.sandbox import CommandSpec, SafePath, SandboxPolicy, SandboxWorkspace


def _policy(**changes: object) -> SandboxPolicy:
    return SandboxPolicy(
        allowed_executables=(Path(sys.executable).name,),
        **changes,
    )


def test_safe_path_rejects_traversal_absolute_and_symlink_escape(tmp_path: Path) -> None:
    workspace = SandboxWorkspace.from_root(tmp_path / "workspace")
    assert workspace.path("nested/file.txt") == workspace.root / "nested" / "file.txt"
    for path in (
        "../outside.txt",
        "..\\outside.txt",
        "/etc/passwd",
        "C:/Windows/system.ini",
        "C:\\Windows\\system.ini",
        "\\\\server\\share",
        "//server/share",
        "nested/../../outside",
        "nested\\..\\..\\outside",
    ):
        with pytest.raises(ValueError):
            workspace.path(path)

    assert workspace.path("src/main.c") == workspace.root / "src" / "main.c"
    assert workspace.path("src\\main.c") == workspace.root / "src" / "main.c"

    outside = tmp_path / "outside"
    outside.mkdir()
    link = workspace.root / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable in this environment")
    with pytest.raises(ValueError):
        SafePath(workspace.root).resolve("link/secret.txt")


def test_zip_traversal_and_symlink_are_rejected(tmp_path: Path) -> None:
    destination = tmp_path / "extract"
    traversal = tmp_path / "traversal.zip"
    with zipfile.ZipFile(traversal, "w") as archive:
        archive.writestr("../escape.txt", "blocked")
    with pytest.raises(EngineeringError) as error:
        SafeArchiveMaterializer().extract(traversal, destination, _policy())
    assert error.value.code is EngineeringErrorCode.ARCHIVE_UNSAFE
    assert not (tmp_path / "escape.txt").exists()

    symlink_archive = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo("link")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(symlink_archive, "w") as archive:
        archive.writestr(info, "../../outside")
    with pytest.raises(EngineeringError) as error:
        SafeArchiveMaterializer().extract(symlink_archive, tmp_path / "symlink-extract", _policy())
    assert error.value.code is EngineeringErrorCode.ARCHIVE_UNSAFE


def test_tar_link_and_archive_budget_are_rejected(tmp_path: Path) -> None:
    link_archive = tmp_path / "link.tar"
    with tarfile.open(link_archive, "w") as archive:
        member = tarfile.TarInfo("link")
        member.type = tarfile.SYMTYPE
        member.linkname = "../../outside"
        archive.addfile(member)
    with pytest.raises(EngineeringError) as error:
        SafeArchiveMaterializer().extract(link_archive, tmp_path / "tar-extract", _policy())
    assert error.value.code is EngineeringErrorCode.ARCHIVE_UNSAFE

    large = tmp_path / "large.zip"
    with zipfile.ZipFile(large, "w") as archive:
        archive.writestr("large.bin", "0123456789")
    with pytest.raises(EngineeringError) as error:
        SafeArchiveMaterializer().extract(
            large, tmp_path / "large-extract", _policy(max_member_bytes=4)
        )
    assert error.value.code is EngineeringErrorCode.RESOURCE_LIMIT_EXCEEDED


def test_structured_command_is_allowlisted_and_shell_free(tmp_path: Path) -> None:
    workspace = SandboxWorkspace.from_root(tmp_path / "workspace")
    executor = StructuredCommandExecutor()
    result = executor.execute(
        CommandSpec(argv=(sys.executable, "-c", "print('ok')")),
        workspace.root,
        _policy(),
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "ok"

    with pytest.raises(EngineeringError) as error:
        executor.execute(CommandSpec(argv=("not-allowlisted",)), workspace.root, _policy())
    assert error.value.code is EngineeringErrorCode.COMMAND_NOT_ALLOWED

    with pytest.raises(EngineeringError) as error:
        executor.execute(
            CommandSpec(argv=(sys.executable, "-c", "print('x')"), network_required=True),
            workspace.root,
            _policy(),
        )
    assert error.value.code is EngineeringErrorCode.NETWORK_DENIED


def test_structured_command_enforces_timeout_output_and_secret_boundaries(tmp_path: Path) -> None:
    workspace = SandboxWorkspace.from_root(tmp_path / "workspace")
    executor = StructuredCommandExecutor()
    with pytest.raises(EngineeringError) as error:
        executor.execute(
            CommandSpec(argv=(sys.executable, "-c", "import time; time.sleep(1)")),
            workspace.root,
            _policy(max_runtime_seconds=0.05),
        )
    assert error.value.code is EngineeringErrorCode.RESOURCE_LIMIT_EXCEEDED

    with pytest.raises(EngineeringError) as error:
        executor.execute(
            CommandSpec(argv=(sys.executable, "-c", "print('x' * 100)")),
            workspace.root,
            _policy(max_output_bytes=4),
        )
    assert error.value.code is EngineeringErrorCode.RESOURCE_LIMIT_EXCEEDED

    with pytest.raises(EngineeringError) as error:
        executor.execute(
            CommandSpec(
                argv=(sys.executable, "-c", "print('ok')"),
                environment={"API_TOKEN": "secret"},
            ),
            workspace.root,
            _policy(),
        )
    assert error.value.code is EngineeringErrorCode.SANDBOX_VIOLATION
