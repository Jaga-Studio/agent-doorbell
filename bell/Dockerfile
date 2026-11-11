FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
# ssh client for ssh wake-ups; ssh refuses to run for a uid without a passwd entry
RUN apt-get update && apt-get install -y --no-install-recommends openssh-client \
    && rm -rf /var/lib/apt/lists/* && useradd -u 1000 -M -d /tmp -s /usr/sbin/nologin bell
WORKDIR /app
COPY bell.py .
USER 1000:1000
CMD ["python", "/app/bell.py"]
