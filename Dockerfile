FROM python:3.12.14-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --system --gid 10001 identitymesh \
    && useradd --system --uid 10001 --gid identitymesh --no-create-home identitymesh

WORKDIR /app

COPY requirements.lock pyproject.toml ./
COPY src ./src

RUN python -m pip install -r requirements.lock \
    && python -m pip install --no-deps .

USER 10001:10001

EXPOSE 8000

CMD ["uvicorn", "identitymesh.main:app", "--host", "0.0.0.0", "--port", "8000"]
