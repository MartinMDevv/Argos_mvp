"""Los detectores de Argos: cada alerta es un plugin (Fase 3).

Este paquete es "donde vive la escalabilidad" según el spec. La forma de sumar una
alerta nueva es crear un archivo acá adentro con una clase decorada con `@registrar`;
nadie tiene que editar el motor, ni una lista, ni el arranque.

    app/detectores/
      base.py           → la clase Detector + qué puede mirar (ContextoDeEvaluacion)
      registro.py       → el decorador @registrar y el descubrimiento automático
      silencio.py       → el antirruido: cuándo callarse aunque haya algo que decir
      motor.py          → quién pregunta, cuándo, y qué hace con la respuesta
      almacen.py        → guardar y leer alertas en TimescaleDB
      umbrales.py       → la configuración de la alerta #1 (memoria + tabla)
      umbral_precio.py  → alerta #1: el precio cruzó una línea que pusiste tú (3.2)
      <detector>.py     → una por alerta (faltan las #2, #3 y #4: pasos 3.3 a 3.5)

Empezá por `base.py`: explica la decisión de fondo (un detector es una función pura de
su contexto) y las dos cadencias.
"""
