def parse_message(message):
    parts = message.split("===")
    try:
        role = parts[1].strip()
        if role == "ASSISTANT MESSAGE":
            role = "assistant"
        elif role == "USER MESSAGE":
            role = "user"
        else:
            role = "other"
        content = parts[-1].strip()
        return {"role": role, "message": content}
    except Exception as e:
        print(f"Error parsing message: {e}")
        raise ValueError(f"Error parsing message: {message}")


def parse_message_history(message_history):
    messages = message_history.split(
        "\n--------------------------------------------------\n"
    )
    parsed_messages = []
    for message in messages:
        message = message.strip()
        if message == "":
            continue
        parsed_messages.append(parse_message(message))

    return parsed_messages


def get_extract_message_outputs(message_history):
    parsed_messages = parse_message_history(message_history)
    is_extract_output = False
    extract_outputs = []
    for message in parsed_messages:
        if message["role"] == "assistant" and "Action: extract" in message["message"]:
            is_extract_output = True
            continue
        if is_extract_output:
            # TODO: This assert might be too strict, maybe relax?
            assert message["role"] == "user"
            extract_outputs.append(message["message"])
            is_extract_output = False

    return extract_outputs
