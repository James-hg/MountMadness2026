from flask import Flask, render_template, jsonify, request

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    """Placeholder chat endpoint - will be replaced by backend team."""
    message = request.json.get("message", "")
    # Mock response for frontend development
    return jsonify(
        {
            "reply": f"This is a placeholder response. Backend will handle: '{message}'"
        }
    )


@app.route("/api/financial-data")
def financial_data():
    """Placeholder financial data endpoint - will be replaced by backend team."""
    # Mock data for frontend development
    return jsonify(
        {
            "labels": ["Week 1", "Week 2", "Week 3", "Week 4", "Week 5", "Week 6", "Week 7", "Week 8"],
            "income": [3200, 3400, 3100, 3600, 3300, 3500, 3800, 3400],
            "outcome": [2100, 2800, 1900, 3200, 2400, 2600, 3100, 2300],
        }
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
