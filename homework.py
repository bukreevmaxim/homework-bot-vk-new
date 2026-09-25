import logging
import os
import random
import sys
import time
from http import HTTPStatus
from logging.handlers import RotatingFileHandler

import requests
import vk_api
from dotenv import load_dotenv

from exceptions import (MissingEnvironmentVariableError,
                        UnexpectedStatusCodeError)

load_dotenv()
RANDOM_ID = random.randint(0, 100000)
PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
VK_TOKEN = os.getenv('VK_TOKEN')
VK_USER_ID = os.getenv('VK_USER_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
# Указываем обработчик логов:
formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s - %(name)s'
)
handler = RotatingFileHandler(
    'my_logger.log',
    maxBytes=50000000,
    backupCount=5,
    encoding='utf-8'
)
handler.setFormatter(formatter)
logger.addHandler(handler)

stream_handler = logging.StreamHandler(stream=sys.stdout)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)


def check_tokens():
    """Выбрасывает ошибку, если нет хотя бы одной переменной окружения."""
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'VK_TOKEN': VK_TOKEN,
        'VK_USER_ID': VK_USER_ID,
    }
    missing_tokens = []
    for token_name, token_value in tokens.items():
        if not token_value:
            missing_tokens.append(token_name)
    if missing_tokens:
        message = 'Отсутствуют переменные окружения: {}'.format(
            ', '.join(missing_tokens)
        )
        logger.critical(message)
        raise MissingEnvironmentVariableError(message)


def send_message(vk, message):
    """Отправляет сообщение в ВК чат.

    Возвращает True, если сообщение успешно доставлено, иначе False.
    """
    try:
        logger.debug('Начинаем отправку сообщения в VK')
        vk.messages.send(
            user_id=VK_USER_ID,
            message=message,
            random_id=RANDOM_ID,
        )
        logger.debug('Сообщение в VK отправлено')
        return True
    except (
        vk_api.exceptions.ApiError,
        requests.exceptions.RequestException,
    ) as error:
        logger.error(f'Сбой при отправке сообщения в VK: {error}')
        return False


def get_api_answer(timestamp):
    """Получает JSON ответ из запроса."""
    # Единый словарь: и в лог, и в запрос попадут одни и те же данные
    request_data = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': timestamp},
    }
    logger.debug(
        'Начинаем запрос к API: {url}, '
        'заголовки: {headers}, параметры: {params}'.format(**request_data)
    )
    try:
        response = requests.get(**request_data)
    except requests.RequestException as error:
        raise ConnectionError(f'Ошибка при запросе к API: {error}')
    if response.status_code != HTTPStatus.OK:
        raise UnexpectedStatusCodeError(
            f'API вернул непредвиденный код ответа: {response.status_code}'
        )
    return response.json()


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError(
            f'Ответ API должен быть словарём, получен тип: '
            f'{type(response).__name__}'
        )
    if 'homeworks' not in response:
        raise KeyError('В ответе API нет ключа "homeworks"')
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError(
            f'"homeworks" должна быть списком, получен тип: '
            f'{type(homeworks).__name__}'
        )
    return homeworks


def parse_status(homework):
    """Формирует сообщение о статусе проверки работы.

    Извлекает из информации о конкретной домашней
    работе статус этой работы.
    """
    if not isinstance(homework, dict):
        raise TypeError(
            f'Данные о домашней работе должны быть словарём, '
            f'получен тип: {type(homework).__name__}'
        )
    if 'homework_name' not in homework:
        raise KeyError('В ответе API отсутствует ключ "homework_name"')
    homework_name = homework['homework_name']
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise KeyError(f'Неизвестный статус домашней работы: {status}')
    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    check_tokens()
    # Создаем сессию для бота
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    timestamp = int(time.time())
    last_error = None

    while True:
        try:
            homework = get_api_answer(timestamp)
            homeworks = check_response(homework)
            if not homeworks:
                logger.debug('В ответе нет новых статусов')
            # Коллекция результатов доставки по каждому вердикту
            send_results = []
            for work in homeworks:
                message = parse_status(work)
                send_results.append(send_message(vk, message))
            # Метку сдвигаем, только если все сообщения доставлены
            if all(send_results):
                timestamp = homework.get('current_date', timestamp)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            if message != last_error:
                if send_message(vk, message):
                    last_error = message
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    try:
        main()
    except MissingEnvironmentVariableError as error:
        logger.critical(error)
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info('Бот остановлен пользователем')
        sys.exit(0)
    except Exception as error:
        logger.critical(f'Необработанная ошибка: {error}')
        sys.exit(1)
