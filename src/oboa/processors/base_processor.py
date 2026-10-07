"""
Executable data-processor helpers for OBOA.
"""

import os
import subprocess

from oboa.engine.errors import ProcessorError


DEFAULT_PROCESSOR_TIMEOUT_SECONDS = 3600


def validate_processor(processor_path):
    """
    Validate that a data processor is an executable file.

    :param processor_path: processor executable path, or None when no processor
        is configured
    :type processor_path: str or None

    :return: True when the processor path is acceptable
    :rtype: bool

    :raises ProcessorError: when the processor path does not exist or is not
        executable
    """
    if processor_path is None:
        return True
    if not os.path.isfile(processor_path):
        raise ProcessorError("The data processor {} does not exist".format(processor_path))
    if not os.access(processor_path, os.X_OK):
        raise ProcessorError("The data processor {} is not executable".format(processor_path))
    return True


def execute_processor(processor_path, processing_path, orchestrated_file,
                      configuration_uuid=None, timeout=DEFAULT_PROCESSOR_TIMEOUT_SECONDS):
    """
    Execute a configured data processor against a staged processing file.

    :param processor_path: executable processor path
    :type processor_path: str
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
    validate_processor(processor_path)
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
            [processor_path, processing_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            timeout=timeout,
            check=False,
            universal_newlines=True,
        )
    except Exception as exc:
        raise ProcessorError("The data processor {} failed to execute: {}".format(processor_path, exc)) from exc

    if result.returncode != 0:
        raise ProcessorError(
            "The data processor {} returned {}. stdout: {} stderr: {}".format(
                processor_path,
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
