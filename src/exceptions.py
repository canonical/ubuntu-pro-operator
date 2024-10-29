# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Custom Exceptions for the Ubuntu Pro charm."""


class ProcessExecutionError(Exception):
    """Exception raised when there is an error executing a process.

    Attributes:
        cmd: The command that was executed.
        ret_code: The return code of the process.
        stdout: The standard output of the process.
        stderr: The standard error of the process.

    """

    def __init__(self, cmd: str, ret_code: int, stdout: str, stderr: str):
        self.cmd = cmd
        self.ret_code = ret_code
        self.stdout = stdout
        self.stderr = stderr
        message = f"Failed running command '{self.cmd}' [exit status: {self.ret_code}].\nstderr: {self.stderr}\nstdout: {self.stdout}"  # noqa
        super().__init__(message)


class APIError(Exception):
    """Exception raised when there is an error with the Pro Client API.

    Attributes:
        error_code: The error code returned by the API.
        message: The error message returned by the API.
    """

    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        self.message = message
        message = f"Error code: {self.error_code}, message: {self.message}"
        super().__init__(message)
