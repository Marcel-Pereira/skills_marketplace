from app import create_app

app = create_app()

if __name__ == "__main__":
    # 0.0.0.0 so the app is reachable from outside a Docker container
    app.run(host="0.0.0.0", port=5001, debug=True)
