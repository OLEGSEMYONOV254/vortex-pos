from openai import OpenAI

client = OpenAI(
    api_key="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",
    base_url="https://openrouter.ai/api/v1"
)

MODEL_NAME = "openchat"  # Или другая модель

def ask_vortex(prompt, system_message="Ты помощник для торговли. Говори на русском, помогай с товарами и кассой."):
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"[ОШИБКА AI]: {e}"
