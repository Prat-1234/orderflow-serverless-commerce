import csv
import io
import os
from datetime import datetime, timezone

import boto3

table = boto3.resource("dynamodb").Table(os.environ["ORDERS_TABLE"])
s3 = boto3.client("s3")


def main():
    items, kwargs = [], {}
    while True:
        page = table.scan(**kwargs)
        items += page["Items"]
        if "LastEvaluatedKey" not in page:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["orderId", "customerId", "status", "orderTotal", "createdAt"])
    for i in items:
        writer.writerow([i.get("orderId"), i.get("customerId"), i.get("status"),
                         i.get("orderTotal", ""), i.get("createdAt")])

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    key = "reports/orders-" + stamp + ".csv"
    bucket = os.environ["REPORT_BUCKET"]
    s3.put_object(Bucket=bucket, Key=key, Body=buf.getvalue().encode())
    print("Wrote " + str(len(items)) + " orders to s3://" + bucket + "/" + key)


if __name__ == "__main__":
    main()
