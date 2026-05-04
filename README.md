# Sistema de Monitoreo Ambiental — DGTIC Supercomputo

<div align="center">

![Estado](https://img.shields.io/badge/Estado-En%20Desarrollo-yellow?style=for-the-badge)
![Institución](https://img.shields.io/badge/UNAM-DGTIC-blue?style=for-the-badge)
![Lenguajes](https://img.shields.io/badge/C%2B%2B%20%7C%20Python%20%7C%20HTML-informational?style=for-the-badge)
![Licencia](https://img.shields.io/badge/Licencia-Académica-green?style=for-the-badge)

**Monitoreo en tiempo real de temperatura y humedad en el área de Supercomputo**

</div>

---

## Información General

| Campo | Detalle |
|---|---|
| **Alumno** | Rodríguez Pichardo Adrián Leonardo |
| **Asesor** | Dr. José Alberto Aparicio Santos |
| **Área** | Supercomputo — DGTIC, UNAM |
| **Modalidad** | Servicio Social |

---

## Descripción del Proyecto

Este repositorio documenta el desarrollo de un **sistema de monitoreo ambiental distribuido** implementado durante el Servicio Social en el área de Supercomputo de la DGTIC. El objetivo principal es supervisar de forma continua las condiciones de temperatura y humedad del centro de datos, generando alertas automáticas ante variaciones críticas que puedan comprometer la infraestructura.

---

## Arquitectura del Sistema

```
┌────────────────────────────────────────────────────────────────────┐
│                        FLUJO DE DATOS                              │
│                                                                    │
│   ┌─────────────┐    HTTP     ┌────────────┐    Query    ┌───────┐ │
│   │  NodeMCU V3 │ ──────────► │            │ ──────────► │       │ │
│   │  + DHT22    │             │ Prometheus │             │       │ │
│   └─────────────┘             │ (Scraping) │             │Grafana│ │
│                               │            │             │       │ │
│   ┌─────────────┐    HTTP     │            │ ──────────► │       │ │
│   │ ESP32-C3    │ ──────────► │            │  Alertas    │       │ │
│   │ Super Mini  │             └────────────┘             └──┬────┘ │
│   │  + DHT22    │                                           │      │
│   └─────────────┘                                     ┌────▼───┐   │
│                                                       │Telegram│   │
│                                                       │ Bot    │   │
│                                                       └────────┘   │
└────────────────────────────────────────────────────────────────────┘
```

### Componentes del Stack

| Capa | Tecnología | Función |
|---|---|---|
| **Recolección** | NodeMCU V3 / ESP32-C3 Super Mini + DHT22 | Exposers de métricas vía HTTP |
| **Almacenamiento** | Prometheus | Scraping y almacenamiento de series de tiempo |
| **Visualización** | Grafana | Dashboards en tiempo real |
| **Alertamiento** | Grafana + Bot de Telegram | Notificaciones ante umbrales críticos |

---

## Hardware Utilizado

### Microcontroladores

- **NodeMCU V3 (ESP8266)** — Recolección de datos con conectividad Wi-Fi integrada
- **ESP32-C3 Super Mini** — Alternativa más compacta y eficiente energéticamente

### Sensores

- **DHT22** — Sensor de temperatura (−40 °C a 80 °C, ±0.5 °C) y humedad relativa (0–100%, ±2–5%)

---

## Estructura del Repositorio

```
SERVICIO-SOCIAL/
│
├── 📂 DOCUMENTOS-SENSORES/
│   └── Investigaciones, diseños y documentación técnica
│       en formato PDF y Word desarrollados durante el proyecto.
│
├── 📂 PROGRAMAS-SENSORES/
│   └── Sketches de Arduino (.ino) para pruebas de sensores
│       y configuración de los microcontroladores.
│
├── 📂 REPORTES-SENSORES/
│   └── Scripts en Python y recursos para el Chatbot de Telegram,
│       incluyendo integración con la API de alertas.
│
└── 📄 README.md
```

---

## Tecnologías y Lenguajes

![C++](https://img.shields.io/badge/C%2B%2B-Arduino-00599C?style=flat-square&logo=cplusplus)
![Python](https://img.shields.io/badge/Python-Telegram%20Bot-3776AB?style=flat-square&logo=python)
![HTML](https://img.shields.io/badge/HTML-Web%20UI-E34F26?style=flat-square&logo=html5)
![Prometheus](https://img.shields.io/badge/Prometheus-Métricas-E6522C?style=flat-square&logo=prometheus)
![Grafana](https://img.shields.io/badge/Grafana-Visualización-F46800?style=flat-square&logo=grafana)

---

## Funcionalidades del Sistema

- Lectura continua de temperatura y humedad con sensores DHT22
- Exposición de métricas en formato compatible con Prometheus vía HTTP
- Scraping automático y almacenamiento histórico con Prometheus
- Dashboards interactivos en tiempo real con Grafana
- Sistema de alertas configurables por umbrales de temperatura
- Notificaciones automáticas vía Bot de Telegram

---

## Actividades Realizadas

A lo largo del Servicio Social se han documentado las siguientes etapas:

1. **Investigación** — Estudio de protocolos IoT, Prometheus y Grafana
2. **Diseño** — Arquitectura de la red de sensores y flujo de datos
3. **Implementación de hardware** — Conexión y prueba de sensores con microcontroladores
4. **Desarrollo de firmware** — Programación de los sketches en Arduino
5. **Integración de monitoreo** — Configuración de Prometheus y Grafana
6. **Desarrollo del Chatbot** — Creación del bot de Telegram en Python para alertas

---

## Institución

Este proyecto se realiza en el marco del Servicio Social universitario dentro de la **Dirección General de Cómputo y de Tecnologías de Información y Comunicación (DGTIC)** de la **Universidad Nacional Autónoma de México (UNAM)**, específicamente en el área de **Supercomputo**.

---

<div align="center">

*Desarrollado con fines académicos e institucionales.*

</div>
