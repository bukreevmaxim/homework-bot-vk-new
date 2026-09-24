class MissingEnvironmentVariableError(Exception):
    """Исключение: отсутствуют обязательные переменные окружения."""

class UnexpectedStatusCodeError(Exception):
    """Исключение: API вернул непредвиденный код ответа."""