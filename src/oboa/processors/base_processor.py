"""
Executable data-processor helpers for OBOA.
"""

import os
import shlex
import shutil
import subprocess

from oboa.engine.errors import ProcessorError


DEFAULT_PROCESSOR_TIMEOUT_SECONDS = 3600
PROCESSOR_FILE_PATH_PARAMETER = "%F"


def _join_command(arguments):
    """
    Join command arguments into a shell-style command string.

    :param arguments: command argument list
    :type arguments: list

    :return: quoted command string
    :rtype: str
    """
    return " ".join(shlex.quote(str(argument)) for argument in arguments)


def split_processor_command(processor_command):
    """
    Split a processor command template into argv-style arguments.

    :param processor_command: processor command template, or None when no
        processor is configured
    :type processor_command: str or None

    :return: command arguments
    :rtype: list

    :raises ProcessorError: when the command cannot be parsed
    """
    if processor_command is None:
        return []
    try:
        arguments = shlex.split(str(processor_command))
    except ValueError as exc:
        raise ProcessorError("The data processor command {} is invalid: {}".format(processor_command, exc)) from exc
    if len(arguments) == 0:
        raise ProcessorError("The data processor command is empty")
    return arguments


def normalize_processor_command(processor_command, configuration_dir=None):
    """
    Validate and normalize a processor command template.

    Only the executable token is resolved to an absolute path. Additional
    command arguments and OBOA parameter placeholders are preserved.

    :param processor_command: processor command template, or None when no
        processor is configured
    :type processor_command: str or None
    :param configuration_dir: directory used to resolve relative executables
    :type configuration_dir: str or None

    :return: normalized command template, or None
    :rtype: str or None

    :raises ProcessorError: when the executable does not exist or is not
        executable
    """
    if processor_command is None or str(processor_command).strip() == "":
        return None
    arguments = split_processor_command(processor_command)
    executable = _resolve_processor_executable(
        arguments[0],
        configuration_dir=configuration_dir,
    )
    _validate_processor_executable(executable)
    arguments[0] = executable
    return _join_command(arguments)


def validate_processor(processor_command):
    """
    Validate that a data processor command starts with an executable file.

    :param processor_command: processor command template, or None when no
        processor is configured
    :type processor_command: str or None

    :return: True when the processor command is acceptable
    :rtype: bool

    :raises ProcessorError: when the command cannot be parsed or the executable
        does not exist or is not executable
    """
    normalize_processor_command(processor_command)
    return True


def build_processor_command(processor_command, file_path):
    """
    Fill OBOA processor parameters and build the command argv.

    ``%F`` is replaced with ``file_path``. For backward compatibility, command
    templates without ``%F`` receive ``file_path`` as the final argument.

    :param processor_command: processor command template
    :type processor_command: str
    :param file_path: staged file path supplied to the processor
    :type file_path: str

    :return: command arguments ready for ``subprocess.run``
    :rtype: list

    :raises ProcessorError: when the command cannot be parsed
    """
    arguments = split_processor_command(processor_command)
    has_file_parameter = any(
        PROCESSOR_FILE_PATH_PARAMETER in argument
        for argument in arguments
    )
    filled_arguments = [
        argument.replace(PROCESSOR_FILE_PATH_PARAMETER, file_path)
        for argument in arguments
    ]
    if not has_file_parameter:
        filled_arguments.append(file_path)
    return filled_arguments


def _validate_processor_executable(processor_path):
    """
    Validate that a data processor executable exists and can be run.

    :param processor_path: processor executable path, or None when no processor
        is configured
    :type processor_path: str or None

    :return: True when the executable path is acceptable
    :rtype: bool

    :raises ProcessorError: when the executable path does not exist or is not
        executable
    """
    if processor_path is None:
        return True
    if not os.path.isfile(processor_path):
        raise ProcessorError("The data processor {} does not exist".format(processor_path))
    if not os.access(processor_path, os.X_OK):
        raise ProcessorError("The data processor {} is not executable".format(processor_path))
    return True


def _resolve_processor_executable(executable, configuration_dir=None):
    """
    Resolve a processor executable from an XML command template.

    Relative executables are resolved against the configuration directory when
    present there. Otherwise, command names can be resolved from ``PATH``.

    :param executable: executable token from the processor command
    :type executable: str
    :param configuration_dir: directory containing the XML configuration
    :type configuration_dir: str or None

    :return: absolute executable path
    :rtype: str
    """
    executable = os.path.expanduser(executable)
    if os.path.isabs(executable):
        return os.path.abspath(executable)

    if configuration_dir is not None:
        configuration_candidate = os.path.join(configuration_dir, executable)
        if os.path.isfile(configuration_candidate):
            return os.path.abspath(configuration_candidate)

    path_executable = shutil.which(executable)
    if path_executable is not None:
        return os.path.abspath(path_executable)

    if configuration_dir is not None:
        return os.path.abspath(configuration_candidate)
    return os.path.abspath(executable)


def execute_processor(processor_command, processing_path, orchestrated_file,
                      configuration_uuid=None, timeout=DEFAULT_PROCESSOR_TIMEOUT_SECONDS):
    """
    Execute a configured data processor against a staged processing file.

    :param processor_command: executable processor command template
    :type processor_command: str
    :param processing_path: staged file path passed to the processor
    :type processing_path: str
    :param orchestrated_file: inventory row for the source file
    :type orchestrated_file: oboa.datamodel.orchestrated_files.OrchestratedFile
    :param configuration_uuid: related orchestration configuration UUID
    :type configuration_uuid: str or uuid.UUID or None
    :param timeout: processor timeout in seconds
    :type timeout: int or float

    :return: processor return code, stdout, and stderr
    :rtype: dict

    :raises ProcessorError: when validation fails, execution fails, times out,
        or returns a non-zero exit status
    """
    processor_description = processor_command
    processor_command = normalize_processor_command(processor_command)
    command = build_processor_command(processor_command, processing_path)
    env = os.environ.copy()
    env.update({
        "OBOA_FILE_UUID": str(orchestrated_file.file_uuid),
        "OBOA_FILE_PATH": processing_path,
        "OBOA_INPUT_PATH": orchestrated_file.path,
        "OBOA_PROCESSING_PATH": processing_path,
        "OBOA_FILE_NAME": orchestrated_file.name,
        "OBOA_FILE_GROUP": orchestrated_file.file_group,
        "OBOA_CONFIGURATION_UUID": "" if configuration_uuid is None else str(configuration_uuid),
    })
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            timeout=timeout,
            check=False,
            universal_newlines=True,
        )
    except Exception as exc:
        raise ProcessorError("The data processor {} failed to execute: {}".format(processor_description, exc)) from exc

    if result.returncode != 0:
        raise ProcessorError(
            "The data processor {} returned {}. stdout: {} stderr: {}".format(
                processor_description,
                result.returncode,
                result.stdout,
                result.stderr,
            )
        )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
