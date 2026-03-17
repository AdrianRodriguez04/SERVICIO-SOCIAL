# SERVICIO SOCIAL - Sistema de Monitoreo de Temperatura y Humedad - DGTIC Supercomputo
## ASESOR: Dr. José Alberto Aparicio SAntos
### ALUMNO: Rodríguez Pichardo Adrián Leonardo
Este repositorio contiene el desarrollo técnico, código fuente y documentación del sistema de monitoreo ambiental realizado durante mi **Servicio Social** en el área de **Supercomputo de la DGTIC**. El objetivo principal es establecer una *red de sensores funcional* que permita la *supervisión constante* y el *alertamiento* temprano ante variaciones críticas de temperatura.
## DESCRIPCIÓN DEL PROYECTO
El sistema utiliza temporalmente microcontroladores *NodeMCU V3* y *ESP32-C3 Super Mini* para la recolección de datos ambientales mediante sensores *DHT22*. La arquitectura está diseñada bajo un modelo:
* **Recolección:** Los dispositivos actúan como exposers de métricas vía HTTP.
* **Almacenamiento:** Prometheus realiza el scraping de los datos en intervalos definidos.
* **Visualización:** Grafana despliega tableros en tiempo real y gestionará el sistema de alertas ante umbrales de temperatura excedidos.
## CONTENIDO DEL REPOSITORIO
* **/DOCUMENTOS-SENSORES:** Archivos en *PDF* y en *WORD* en donde se redactan las actividades realizadas durante el desarrollo del proyecto, tales como investigaciones, documentaciones, diseños, etc.
* **/PROGRAMAS-SENSORES:** Archivos en *ARDUINO* que se han realizado para las pruebas de los sensores y microcontroladores.
