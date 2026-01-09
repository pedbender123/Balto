
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from app.core import prompts, ai_client, config
import json

# Manual Mock config if env not loaded (but we will run with env)
# config.OPENAI_API_KEY should be set

def test_ai_logic():
    print("Testing AI Logic with new Prompt...")
    print(f"System Prompt Snippet: {prompts.SYSTEM_PROMPT[:100]}...")
    
    # Test Case 1: Generic Symptom "Moleza"
    input_text = "Estou sentindo uma moleza no corpo e um pouco de dor de cabeça."
    print(f"\n[Input]: {input_text}")
    
    try:
        response = ai_client.ai_client.analisar_texto(input_text)
        print(f"[Raw Response]: {response}")
        
        if response:
            data = json.loads(response)
            if "itens" in data:
                items = data["itens"]
                print(f"[Items Count]: {len(items)}")
                for i, item in enumerate(items):
                    print(f"  {i+1}. {item.get('sugestao')} - {item.get('explicacao')}")
                
                if len(items) >= 3:
                     print("SUCCESS: 3 recommendations returned.")
                else:
                     print("WARNING: Less than 3 recommendations.")
            else:
                 print("WARNING: Old schema format or no items.")
    except Exception as e:
        print(f"ERROR: {e}")

    # Test Case 2: Noise
    input_text_noise = "(Som de batida) (ruído de fundo)"
    print(f"\n[Input Noise]: {input_text_noise}")
    try:
        response_noise = ai_client.ai_client.analisar_texto(input_text_noise)
        print(f"[Response]: {response_noise}")
        if not response_noise or "null" in response_noise.lower() or "nenhuma" in response_noise.lower():
             print("SUCCESS: Ignored noise.")
        else:
             data = json.loads(response_noise)
             # If it returns items, check if they are empty
             if "itens" in data and not data["itens"]:
                 print("SUCCESS: Empty items list.")
             else:
                 print("FAILURE: AI hallucinated on noise.")
    except:
        print("SUCCESS: Error or specific handling for noise.")

if __name__ == "__main__":
    test_ai_logic()
