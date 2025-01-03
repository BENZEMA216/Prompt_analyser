if __name__ == "__main__":
    interface = create_ui()
    interface.launch(
        server_name="0.0.0.0",
        server_port=7860,
        auth=("admin", "password"),
        debug=False
    ) 