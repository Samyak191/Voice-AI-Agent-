import uuid

SYSTEM_PROMPT = (
    "You are a warm, natural-sounding voice assistant having a real spoken "
    "conversation, not writing a document. Speak the way a helpful person "
    "would speak out loud: short sentences, casual and conversational, no "
    "headers, no bullet points, no markdown formatting, no numbered lists. "
    "Keep responses brief and to the point, usually two to four sentences, "
    "unless the user clearly asks for more detail. If something has many "
    "parts, mention just the most useful one or two instead of listing "
    "everything. Talk like you're chatting with a friend, not presenting "
    "a report."
)


class Session:
    def __init__(self):
        self.id = str(uuid.uuid4())
        self.generation = 0
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.active = False

    def new_generation(self):
        self.generation += 1
        return self.generation

    def add_turn(self, role, text):
        self.history.append({"role": role, "content": text})
        if len(self.history) > 20:
            self.history = [self.history[0]] + self.history[-19:]