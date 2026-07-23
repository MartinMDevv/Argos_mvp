# AGENTS.md — Contexto del agente · Argos

Punto de entrada de contexto: léelo primero y siempre. Solo lo esencial + el índice (§9); salta a
un doc enlazado solo cuando necesites su detalle. Mantener corto.

## 1. Qué es
Argos: asistente personal de inteligencia de mercado cripto. Vigila en tiempo real, detecta lo
anómalo (precio/volatilidad/volumen), lo explica y avisa. Lema: "Argos lo ve primero".

## 2. Regla de oro (inviolable)
La IA nunca inventa números. Probabilidades/porcentajes salen de estadística sobre datos históricos
reales; la IA solo los traduce a lenguaje natural. Sin dato, decir "no hay dato"; no suponer.

## 3. Guardarraíles
- Foco MVP = solo BTC/ETH. Memecoins/Solana/on-chain/social/portafolio = "fase futura": se anotan, no se implementan.
- No inventar APIs, endpoints, columnas de BD, librerías ni datos; verificar contra código/docs reales. Ante duda, decirlo.
- Bajo ruido > volumen de alertas.
- Cambios pequeños y verificables, cada paso con un check concreto.
- No es consejo financiero: contexto y números; decide el usuario.

## 4. Estilo de trabajo
Español, didáctico paso a paso, comentarios de código en español. Explicar antes de ejecutar;
confirmar antes de commitear. Sin firma de Claude / Co-Authored-By. Docker manual (docker-on/off;
no systemctl enable). Ritmo por paso: explico -> construyo -> verificamos -> commiteas.

## 5. Stack
Python + FastAPI (async) · TimescaleDB (Docker) · detectores como plugins (numpy/scipy) ·
Ollama (7-8B cuantizado, RTX 3060) · aiogram (Telegram) · React + TS + Vite + Tailwind ·
lightweight-charts · Docker Compose.

## 6. Arquitectura
Monolito modular, fronteras limpias. Detectores como plugins (agregar = enchufar, no reescribir).
Núcleo agnóstico de usuario (multiusuario/suscripción se añade encima, después).

## 7. Estado y norte
Fase 0 (cimientos): 0.1 hecho (esqueleto + git); siguiente 0.2 TimescaleDB. Estado tildable en
CHECKLIST.md. Norte: MVP (v1.0) primero; el mercado se expande por versiones (v1.1 -> v5.0) hasta un
posible producto con suscripción. El motor del MVP se reutiliza en cada fase, no se reescribe.

## 8. Índice de documentos
Salta a un doc solo si necesitas su detalle. Conforme avance el proyecto se agregan aquí los MD de avance.

| Documento | Qué contiene | Cuándo saltar |
|---|---|---|
| [`../../spec-crypto-monitor.md`](../../spec-crypto-monitor.md) | Spec completo: idea, metas, MVP, taxonomía de alertas, stack, roadmap v1→v5 | Dudas de alcance, diseño o el "por qué" de una decisión |
| [`./CHECKLIST.md`](./CHECKLIST.md) | Dinámica de trabajo + pasos tildables del MVP | Saber qué toca ahora o el estado de avance |
| [`../README.md`](../README.md) | Presentación del repo, estructura y cómo levantarlo | Onboarding rápido o comandos de arranque |
| *(avance-fase-N.md)* | *(Notas de avance por fase — se enlazan aquí al crearlas)* | Detalle de lo hecho en una fase concreta |
