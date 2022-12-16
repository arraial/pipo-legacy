FROM python:3.9.16-slim-bullseye as base

    # python
ENV APP_NAME="pipo" \
    PYTHON_VERSION=3.9.16 \
    PYTHONUNBUFFERED=1 \
    # prevents python creating .pyc files
    PYTHONDONTWRITEBYTECODE=1 \
    \
    # pip
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    # fixes install error for cryptography package, as does locking cryptography version
    CRYPTOGRAPHY_DONT_BUILD_RUST=1 \
    \
    # poetry
    # https://python-poetry.org/docs/configuration/#using-environment-variables
    POETRY_VERSION=1.2.2 \
    # make poetry install to this location
    POETRY_HOME="/opt/poetry" \
    # make poetry create the virtual environment in the project's root
    # it gets named `.venv`
    POETRY_VIRTUALENVS_CREATE=true \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    # do not ask interactive questions
    POETRY_NO_INTERACTION=1 \
    \
    # paths
    # where requirements + virtual environment will be
    PYSETUP_PATH="/opt/pysetup" \
    VENV_PATH="/opt/pysetup/.venv"

    # prepend poetry and venv to path
ENV PATH="$POETRY_HOME/bin:$VENV_PATH/bin:$PATH"

# install required system dependencies
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get --no-install-recommends install -y \
        ffmpeg \
    && pip3 install --upgrade pip setuptools wheel \
    && apt-get clean


# `builder-base` stage is used to build deps + create virtual environment
#FROM base as builder-base
FROM base as builder-base

# gcc and python3-dev will be used for proj dependencies install, not being removed here
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install --no-install-recommends -y \
        make \
        gcc \
        libc-dev \
        libssl-dev \
        # discord.py[voice] dependencies
        python3-dev \
        libffi-dev \
        libnacl-dev \
    && apt-get clean \
    && pip3 install --ignore-installed distlib --disable-pip-version-check \
        cryptography==3.4.6 \
        poetry==$POETRY_VERSION

# copy project requirement files to ensure they will be cached
WORKDIR $PYSETUP_PATH
COPY pyproject.toml ./

# install runtime dependencies, internally uses $POETRY_VIRTUALENVS_IN_PROJECT
RUN poetry install --without dev


# `production` image used for runtime
FROM base as production

# app configuration
ENV ENV=production \
    USERNAME=appuser \
    USER_UID=1000
ENV USER_GID=$USER_UID

RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME
USER $USERNAME

COPY --from=builder-base --chown=$USERNAME:$USERNAME $PYSETUP_PATH $PYSETUP_PATH
COPY ./${APP_NAME} /${APP_NAME}/

ENTRYPOINT $VENV_PATH/bin/python -m $APP_NAME
