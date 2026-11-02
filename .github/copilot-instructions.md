# Gestor de incidencias (Python) 
## Qué es 
Aplicación web para registrar incidencias informáticas. El usuario solo escribe 
la observación; la aplicación la clasifica con un modelo local de LM Studio. 
## Entorno - Python 3.11 o superior, entorno virtual en .venv - Dependencias en requirements.txt (no añadas otras sin preguntar) - Base de datos SQLite en un único archivo (incidencias.db) 
## Cómo se ejecuta y se prueba - Arrancar: <comando que decidáis, p. ej. flask --app app run> - Tests: pytest (deben pasar antes de dar un paso por terminado) - Editor: Visual Studio Code. Crea .vscode/launch.json para arrancar y 
depurar la aplicación con F5, y configura pytest en el panel Testing. 
## Modelo de IA - Se usa SIEMPRE el servidor local de LM Studio: http://localhost:1234/v1 
con el cliente "openai" de Python. NO uses Ollama ni APIs en la nube. - El identificador del modelo y la URL se leen de variables de entorno 
(LMSTUDIO_URL, LMSTUDIO_MODEL), con esos valores por defecto. 
## Convenciones
 Código y nombres en español o inglés, pero coherentes en todo el proyecto. - Toda la llamada al modelo va en un único módulo (clasificador.py). - Un commit por cada paso terminado, con mensaje descriptivo. 
  
## No hacer - No guardes contraseñas en claro. - No borres la base de datos ni el historial de git.