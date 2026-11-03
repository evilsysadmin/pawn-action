# Pawn Action · revisión visual del traslado

Esta migración **no queda aprobada solo porque la CI de Godot sea verde**.
La PR de extracción permanece en Draft hasta contrastar capturas reales
con el último baseline visual de Chess Studio aceptado explícitamente.

## Evidencia real por SHA

El workflow `Pawn Action · Godot / Web CI` exporta Godot 4.7.2, ejecuta
Chromium con ratón, teclado y touch, y guarda el artifact
`pawn-action-real-visual-evidence`. Después genera un paquete
`review/` dentro del mismo artifact:

- `review-desktop.jpg`: idle, carrera, disparo, crouch, SMG,
  salto/aterrizaje y escenario industrial con tramo de travesía
- `review-closeups.jpg`: anclajes y escala de Matthias entre armas
- `review-motion.jpg`: secuencia temporal de carrera y salto extraída de frames
  reales de screencast del compositor Chromium en una zona despejada,
  acreditado por evento real de Godot tras subir al menos 80 px y aterrizar
- `review-mobile.jpg`: landscape listo, disparo real,
  lanzamiento de granada por touch, recarga y aviso de rotación portrait
- `review-manifest.json`: SHA exacto del HEAD de la PR (no el SHA del
  merge sintético de GitHub), run ID, dimensiones y SHA-256 del
  PNG **original** para cada captura usada
- `README.md`: instrucciones de revisión y estado pendiente

Se valida también la subida física y aterrizaje en `runtime-visual-health.json`
mediante los eventos `player-airborne` y `player-landed` de Godot (no basta
con pulsar SPACE ni etiquetar un fotograma como salto). La captura de aterrizaje
sigue al actor en vez de mostrar un recorte vacío.

Se valida también el manifest de captura real `runtime-visual-health.json`
y la prueba móvil `mobile-web-smoke.json`. Un frame obligatorio ausente,
manifiesto duplicado, screenshot corrupto, dimensiones equivocadas, un
toque que no dispare, granada sin evento real o una prueba de orientación fallida hacen que el
paso del review falle. El artifact crudo se sube incluso al fallar para
diagnóstico. La retención sube de 5 a 21 días para permitir la revisión.

## Comparación que falta

Los JPG son hojas de contacto **generadas de los PNG reales**,
no mockups ni sprites authored. El paquete marca expresamente
`review_pending` y `baseline.not_supplied`.

Para aceptar la extracción, recuperar un **baseline de Chess Studio
con SHA, run, viewport, escenario y estado comprobables**, enseñar
ambas versiones lado a lado y revisar al menos la escala canónica,
pivot/footline, siluetas, doble arma, alpha, jitter, carrera/disparo,
SMG, salto, clipping, HUD, escenarios y controles móviles.

No se puede inferir la aceptación visual de una comparación de hashes,
de una imagen vieja sin procedencia ni de una CI verde. Las capturas
deben verse **en el chat de revisión**, además de estar enlazadas en
GitHub Actions; el reviewer debe poder inspeccionarlas realmente.
No poner Ready ni habilitar automerge para la PR de extracción hasta
esa revisión y el cierre del ownership de R2/staging.

El paquete no modifica sprites, escenas, gameplay ni el legacy runtime
de Chess Studio; no dispara despliegues ni escribe en R2.
