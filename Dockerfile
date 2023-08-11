FROM python:3.8-slim

ENV APP_HOME /app
WORKDIR $APP_HOME
COPY . ./


RUN pip install -r requirements.txt
RUN pip install --no-deps -r requirements-no-deps.txt

ENV PORT 8080
EXPOSE 8080

CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 app:app
