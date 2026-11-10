import os

from flask import Flask
from flask_pymongo import PyMongo
from pymongo.errors import PyMongoError

app = Flask(__name__)
app.config["MONGO_URI"] = os.environ.get("MONGO_URI", "mongodb://mongo:27017/tp-docker")
mongo = PyMongo(app, serverSelectionTimeoutMS=5000)


@app.route("/")
def hello():
    try:
        mongo.cx.admin.command("ping")
        document = mongo.db.visits.find_one({"_id": "counter"})
        count = document["visit_count"] if document else 0
        mongo.db.visits.update_one(
            {"_id": "counter"},
            {"$inc": {"visit_count": 1}},
            upsert=True, # if the document does not exist, create it
        )
    except PyMongoError as error:
        return f"Connection to MongoDB failed: {error}", 500

    return f"Connected to MongoDB! {count + 1} visits stored in MongoDB."


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
