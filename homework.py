from dotenv import load_dotenv
import os
import vk_api
import time
import requests
import random
import logging
from logging.handlers import RotatingFileHandler
import sys

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
    backupCount=5
)
handler.setFormatter(formatter)
logger.addHandler(handler)

stream_handler = logging.StreamHandler(stream=sys.stdout)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)


def check_tokens():
    """Выбрасывает ошибку, если нет хотя бы одной переменной окружения."""
    if not all([PRACTICUM_TOKEN, VK_TOKEN, VK_USER_ID]):
        logger.critical('Отсутствует обязательная переменная окружения')
        raise SystemExit('Отсутствует обязательная переменная окружения')


def send_message(vk, message):
    """Отправляет сообщение в ВК чат."""
    try:
        vk.messages.send(
            user_id=VK_USER_ID,
            message=message,
            random_id=RANDOM_ID,
        )
        logger.debug('Сообщение в VK отправлено')
    except Exception as error:
        logger.error(f'Сбой при отправке сообщения в VK: {error}')
        raise


def get_api_answer(timestamp):
    """Получает JSON ответ из запроса."""
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp}
        )
    except requests.RequestException as error:
        logger.error(f'Ошибка при запросе к API: {error}')
        raise ConnectionError(f'Ошибка при запросе к API: {error}')
    if response.status_code != 200:
        logger.error(
            f'Эндпоинт недоступен, код ответа: {response.status_code}'
        )
        raise ValueError(f'Ошибка API: {response.status_code}')
    return response.json()


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError('Ответ API должен быть словарём')
    if 'homeworks' not in response:
        logger.error('В ответе API нет ключа "homeworks"')
        raise KeyError('В ответе нет ключа "homeworks"')
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError('"homeworks" должна быть списком')
    return homeworks


def parse_status(homework):
    """Формирует сообщение о статусе проверки работы.

    Извлекает из информации о конкретной домашней
    работе статус этой работы.
    """
    if 'homework_name' not in homework:
        raise KeyError('В ответе API отсутствует ключ "homework_name"')
    homework_name = homework['homework_name']
    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        logger.error(f'Неизвестный статус домашней работы: {status}')
        raise KeyError(f'Неизвестный статус: {status}')
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
            for i in homeworks:
                message = parse_status(i)
                send_message(vk, message)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            if message != last_error:
                try:
                    send_message(vk, message)
                except Exception as vk_error:
                    logger.error(
                        f'Не удалось сообщить об ошибке в VK: {vk_error}'
                    )

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
