"""Ingesta: la puerta de entrada de los datos reales del mercado a Argos.

Cada módulo de acá adentro habla con UNA fuente externa (hoy: Binance) y la traduce a
los modelos de dominio de `app.modelos`. El resto de Argos consume esos modelos y no
sabe —ni le importa— de dónde salieron.
"""
