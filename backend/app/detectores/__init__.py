"""Los detectores de Argos: cada alerta es un plugin (Fase 3).

Este paquete es "donde vive la escalabilidad" según el spec. La forma de sumar una
alerta nueva es crear un archivo acá adentro con una clase decorada con `@registrar`;
nadie tiene que editar el motor, ni una lista, ni el arranque.

    app/detectores/
      base.py       → la clase Detector + qué puede mirar (ContextoDeEvaluacion)
      registro.py   → el decorador @registrar y el descubrimiento automático
      silencio.py   → el antirruido: cuándo callarse aunque haya algo que decir
      motor.py      → quién pregunta, cuándo, y qué hace con la respuesta
      almacen.py    → guardar y leer alertas en TimescaleDB
      <detector>.py → uno por alerta (pasos 3.2 a 3.5)

Empezá por `base.py`: explica la decisión de fondo (un detector es una función pura de
su contexto) y las dos cadencias.
"""
