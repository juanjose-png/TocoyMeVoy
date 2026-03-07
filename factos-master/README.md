# Quick start

1. Create an environment with pyenv tool by configured with python3.10

    - Install python 3.10 version `pyenv install 3.10`
    - Active local version of python `pyenv local 3.10`
    - Install virtualenv module if it is not installed `python -m pip install virtualenv`
    - Create a virtual environment `python -m virtualenv ~/.virtualenvs/factos`

2. Prepare virtual environment
    - Active environment `source ~/.virtualenvs/factos/bin/activate`
    - Install depencencies `pip install -r requirements.txt`

3. Start Redis service with [Storage Services](https://gitlab.com/unergy-dev/dev-tools/storage-services)

4. Create a .env file

    - Copy the `.env.example` file to `.env` and set the necessary environment variables.
    - Make sure to set the `REDIS_HOST` and `REDIS_PORT` variables to match your Redis service configuration.

5. Make Docker image
    - The `${IMAGE}` variable is in .env file and the value can be literally put in the command
        ```bash
        docker build -t factos-backend:1.0.0 --build-arg USER_ID=$(id -u) --build-arg GROUP_ID=$(id -g) .
        ```


# There is 2 ways to start the project, in local development or in Docker.

## 1. Start in local development
1.1. Active the virtual environment
    ```
    source ~/.virtualenvs/factos/bin/activate
    ```

NOTE: Make migrations to create DB or request the db.sqlite3 file if it does not exist.

1.2. Run the command to apply migrations
    ```
    python manage.py migrate
    ```

1.3. Run the command to start Django service
    ```
    python manage.py runserver
    ```

1.4. Run the command to start Celery worker
    ```
    celery -A factos worker -l INFO --queues=invoice_processing,celery
    ```

1.5. Run the command to start Celery Beat
    ```
    celery -A factos beat -l INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler
    ```

## 2. Start in Docker
2.1. Change the redis configuration in the `.env` file to match the Docker service configuration:
```
REDIS_HOST='redis'
REDIS_PORT='6379'
```

2.2. Start services

    1. To start the services is necessary to setting variables for Postgres and Redis. To do that run the bellow commands

        ```bash
        docker compose up -d
        ```

    2. To stop the services, run the bellow commands
        ```bash
        docker compose down
        ```

