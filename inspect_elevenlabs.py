from elevenlabs import ElevenLabs
import inspect

try:
    client = ElevenLabs(api_key="test_key")
    print("Client attributes:")
    print(dir(client))
    
    if hasattr(client, 'text_to_speech'):
        print("\nclient.text_to_speech attributes:")
        print(dir(client.text_to_speech))

    if hasattr(client, 'generate'):
        print("\nclient.generate exists")
    else:
        print("\nclient.generate DOES NOT exist")
        
except Exception as e:
    print(e)
