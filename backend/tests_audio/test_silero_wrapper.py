import sys
import os

# Add backend directory to path so we can import app
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.silero_vad import SileroVAD

def test_loading():
    print("Iniciando teste de carregamento do SileroVAD Wrapper...")
    try:
        vad = SileroVAD()
        print("Wrapper instanciado com sucesso!")
        
        # Opcional: verificar se o modelo está carregado checando algum atributo
        if hasattr(vad, 'model'):
            print("Modelo presente no objeto.")
        else:
            print("AVISO: Modelo não encontrado no objeto.")
            
    except Exception as e:
        print(f"ERRO CRÍTICO ao carregar wrapper: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    test_loading()
