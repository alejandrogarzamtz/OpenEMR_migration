import argparse
import signal
import time

from .config import settings
from .db import SessionLocal
from .services.delivery_worker import process_outbox
from .services.extensions import process_webhook_deliveries

running=True


def stop(*_):
    global running
    running=False


def process_once(limit:int)->dict:
    with SessionLocal() as db:
        webhooks=process_webhook_deliveries(db,limit)
    outbox={"processed":0,"sent":0,"failed":0,"deferred":0}
    if settings.notification_delivery_mode!="disabled":
        with SessionLocal() as db:outbox=process_outbox(db,limit)
    return {"webhooks":webhooks,"outbox":outbox}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--interval",type=int,default=5);parser.add_argument("--limit",type=int,default=100);parser.add_argument("--once",action="store_true");args=parser.parse_args()
    if args.interval<1 or args.limit<1:parser.error("interval and limit must be positive")
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    while running:
        process_once(args.limit)
        if args.once:break
        time.sleep(args.interval)


if __name__=="__main__":main()
