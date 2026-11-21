FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY clipbot ./clipbot
RUN pip install --no-cache-dir .
# data/ holds the database, logins and logs; output/ holds finished videos.
VOLUME ["/app/data", "/app/output"]
CMD ["clipbot", "run"]
