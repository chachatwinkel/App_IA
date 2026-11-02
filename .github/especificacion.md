## Funcionalidad: registro y clasificación automática de incidencias 
  
Usuarios y roles - Dos roles: "usuario" y "tecnico". Usuarios de prueba creados al arrancar. - Login con usuario y contraseña (contraseñas con hash). 
  
Registrar una incidencia (rol usuario) - Formulario con un único campo de texto: "Observación". - Al enviarla, la app llama al modelo de LM Studio y guarda: 
  fecha, usuario, observación, categoria, prioridad, resumen y estado ("abierta"). - El usuario ve la lista de SUS incidencias con su estado. 
  
Clasificación - categoria: hardware | software | red | cuenta - prioridad: baja | media | alta - resumen: máximo 15 palabras - Salida estructurada (response_format con json_schema), temperatura 0. - Si la respuesta no es válida, reintenta una vez; si vuelve a fallar 
  o LM Studio no responde, guarda la incidencia con categoria "revisar". 
  La incidencia nunca se pierde. 
  
Panel del técnico - Lista de todas las incidencias, filtrable por categoría, prioridad y estado. - Puede corregir la categoría y la prioridad y cambiar el estado 
  (abierta, en curso, resuelta). 
  
Criterios de aceptación 
1. Con LM Studio parado, registrar una incidencia no da error 500: 
   se guarda con categoria "revisar". 
2. "No arranca el portátil, no enciende ni el led" se clasifica como hardware. 
3. Un usuario no puede ver las incidencias de otro usuario. 
4. Un usuario sin rol técnico no puede entrar en el panel del técnico. 
5. Los tests de clasificar() usan un modelo simulado (no necesitan LM Studio). 