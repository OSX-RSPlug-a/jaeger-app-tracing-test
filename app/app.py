import datetime
import logging
import os
import requests
import time

import redis
import redis_opentracing
from flask import Flask, jsonify
from flask_opentracing import FlaskTracing
from jaeger_client import Config

app = Flask(__name__)

redis_db = redis.Redis(host="redis-primary.default.svc.cluster.local", port=6379, db=0)
redis_db.set("last_access", str(datetime.datetime.now()))


def init_tracer(service):
    logging.getLogger("").handlers = []
    logging.basicConfig(format="%(message)s", level=logging.DEBUG)

    config = Config(
        config={"sampler": {"type": "const", "param": 1}, "logging": True},
        service_name=service,
    )

    # this call also sets opentracing.tracer
    return config.initialize_tracer()


# starter code
jaeger_tracer = init_tracer("test-service")
flask_tracer = FlaskTracing(jaeger_tracer, True, app)
redis_opentracing.init_tracing(jaeger_tracer, trace_all_classes=False)

with jaeger_tracer.start_span("first-span") as span:
    span.set_tag("first-tag", "100")


def do_heavy_work():
    pass


@app.route("/")
@flask_tracer.trace()
def hello_world():
    return "Hello World!"


@app.route("/alpha")
@flask_tracer.trace()
def alpha():
    with jaeger_tracer.start_span("alpha-endpoint") as span:
        count = 100
        timer = 10
        span.set_tag("iter-tot-count", count)
        for i in range(count):
            with jaeger_tracer.start_span(f"iter_{i}", child_of=span) as site_span:
                do_heavy_work()
                if i % 100 == 99:
                    time.sleep(timer)
                    site_span.set_tag("request-duration", f"{timer}")

    return "This is the Alpha Endpoint!"


@app.route("/beta")
@flask_tracer.trace()
def beta():
    with jaeger_tracer.start_span("get-google-search-queries") as span:
        a_dict = {}
        req = requests.get("https://www.google.com/search?q=python")
        span.set_tag("jobs-count", len(req.json()))
        span.log_kv({"event": "req-status", "result": req.status_code})
        if req.status_code == 200:
            span.set_tag("request-type", "Success")
        else:
            print("Unable to get site")
            span.set_tag("request-type", "Failure")

        for key, value in req.headers.items():
            print(key, ":", value)
            span.log_kv({"event": "headers", "result": f"{key}: {value}"})
            with jaeger_tracer.start_span(key["Date"], child_of=span) as date_span:
                date_span.set_tag("date-change", "Success")
            a_dict.update({key: value})
    return jsonify(a_dict)


# needed to rename this view to avoid function name collision with redis import
@app.route("/writeredis")
def writeredis():
    # start tracing the redis client
    redis_opentracing.trace_client(redis_db)
    r = requests.get("https://www.google.com/search?q=python")
    a_dict = {}

    # put the first 50 results into a_dict
    for key, value in list(r.headers.items())[:50]:
        print(f"{key}: {value}")
        a_dict.update({key: value})

    try:
        redis_db.mset(a_dict)
    except redis.exceptions.ConnectionError as err:
        print(err)

    return jsonify(a_dict)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
