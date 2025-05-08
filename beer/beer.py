from flask import Flask, jsonify
app = Flask(__name__)

breweries = [
    {"name": "Tree House", "lat": 42.13679801905403, "long": -72.0123901407236},
    {"name": "Trillium", "lat": 42.352513670121645, "long": -71.04749252578482},
    {"name": "Yards", "lat": 39.96118386082349, "long": -75.14695123676813},
    {"name": "Equilibrium", "lat": 41.444799039800664, "long": -74.41979249157365},
    {"name": "Suarez Family", "lat": 42.111148113326124, "long": -73.81232254551149},
    {"name": "Hudson Valley", "lat": 41.501638564463704, "long": -73.9630373897188}
]

@app.route("/api/breweries")
def get_breweries():
    return jsonify(breweries)

if __name__ == "__main__":
    app.run()

