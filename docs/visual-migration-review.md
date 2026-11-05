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
- `review-closeups.jpg`: anclajes y escala de Matthias entre armas; incluye
  close-up tras recoger la SMG real (x=1240)
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

## Candidato Web vivo de Chess Studio (no aprobado)

La CI de Pawn Action incorpora una captura de referencia **solo de lectura**
mediante `scripts/pawn_action_legacy_baseline_capture.mjs`. Consulta
exclusivamente `https://assets.chess-studio.shadowops.dpdns.org/pawn-slug-godot/current.json`,
valida el `sourceSha` de 40 caracteres, el release inmutable, host, claves y
SHA-256/bytes reales de `index.html`, `index.js`, `index.wasm` e
`index.pck` **antes de abrir Chromium**. No utiliza tokens ni escribe en R2.

Captura idle, carrera, carrera+disparo y paisaje móvil. Para SMG usa el
**pickup real del mapa industrial en x=1240**: posiciona a Matthias cerca
mediante el probe de posición ya existente, espera el `ready` normal de
pistola, desplaza al jugador mediante teclado real, exige el evento
`weapon-changed` tras recoger el arma y, finalmente, exige `player-fired`
**después** de la recogida. El disparo demuestra que Godot ha recuperado
su `visual_ready()`, a diferencia del antiguo `weaponProbe=machinegun`
en cold boot, que podía emitir `weapon-changed` con canvas negro.
Pawn Action reproduce la **misma ruta** (spawn x=1170, pickup x=1240,
1280×720, teclado real, parar con `weapon-changed` y disparar tras
equipar), y exige `ready`, `weapon-pickup`, `weapon-changed` y
`player-fired`. Su nueva captura `57-smg-pickup-matched.png` y
close-up están fijados al SHA en el manifest de revisión y la comparación
rechaza un PNG sin hash válido. La posición se controla por el mismo
inicio y evento; **no** se finge identidad de fotograma ni tiempo de animación.
El método no modifica ni inyecta código en el export Web legado.

Si el pickup o el disparo no se acreditan, registra estado
`candidate_partial_not_approved`, eventos/errores y
`smg-unverified-diagnostic.png`; no etiqueta un arma no probada.
El artifact separado
`pawn-action-legacy-visual-candidate` contiene `baseline-candidate.json`
con hashes de capturas, procedencia del puntero y
`side-by-side-candidate.jpg` frente a las capturas del HEAD actual.
Las escenas y viewports son comparables, pero los tiempos de movimiento
son independientes y no equivalen a una referencia frame-locked.

El servicio legacy es externo al repo nuevo; el step es opcional y
`continue-on-error` para no convertir un fallo temporal de su CDN en un
falso fallo de las pruebas propias de Pawn Action. Un puntero inválido o error de captura base retiene `baseline-error.json` y
no produce comparación. Si solo falla el SMG, se publica **únicamente** la
comparación parcial de los cuatro estados con hashes comprobados, señalando
el bloqueo explícitamente. Ninguna de estas situaciones aprueba la migración;
la PR sigue en Draft.

Una captura fresca del release vivo es una *candidata verificable*, nunca
una aprobación retrospectiva del baseline artístico de Chess Studio.
La aceptación visual manual debe inspeccionar la comparación en el chat y
conservar la autoridad de revisión separada de la CI.

## Salto real comparado con referencia histórica

La CI también compara el salto con **pistola y salida industrial x=110** en
ambas versiones (1280×720, Space sostenido 850 ms, sin desplazar cámara).
Guarda fotogramas PNG originales del compositor Chromium y selecciona el
ápice a partir de los píxeles reales de Matthias: exige un ascenso de al
menos 80 píxeles y retorno al suelo, sin editar ni sintetizar imágenes.
El antiguo shell Web devuelve a veces screencast 800×600 de la esquina
superior izquierda (e incluso un primer frame 800×450) aun con viewport
1280×720; se descartan los que recortan la región de Matthias y se
conservan **los originales sin escalar**. El manifest registra el tamaño
real de cada fuente y el fotograma seleccionado. La cantidad de frames
puede variar por compositor: se requieren al menos seis frames originales
(cinco con la región completa de Matthias), pero **siempre** se exige
ascenso real >=80 px y regreso al suelo. No basta con un número de
fotogramas, una tecla pulsada o un frame aislado. El montaje usa recortes
**de las mismas coordenadas de píxel** alrededor del actor en ambas
versiones, evitando falsas diferencias de escala por el tamaño del frame.

Chess Studio (octubre 2026) no expone el evento `player-airborne`;
se valida el desplazamiento observado en los PNG. Pawn Action requiere
además sus eventos físicos `player-airborne` y `player-landed`.
Los SHA-256 de ambos juegos, la posición inicial, el ápice, el aterrizaje
y el frame de origen constan en los manifiestos. Incluso si el SMG legado
falla intermitentemente, el estado parcial debe conservar los saltos
físicamente acreditados y NO debe marcar el SMG como aprobado.
Esto aporta evidencia comparable, no sincronía de fotograma ni aceptación
artística humana.

## Carrera y disparo · secuencia temporal original

El artifact histórico añade `side-by-side-motion-candidate.jpg` con
cuatro muestras de la carrera y otras cuatro de carrera con FIRE mantenido,
todas desde capturas Chromium **reales**, sin interpolación, y junto a
los mismos índices de las capturas Web de Pawn Action. El montaje exige
viewport 1280×720, valida el SHA-256 de cada PNG original en el manifest
histórico y en el review vinculado al HEAD actual, y usa coordenadas de
recorte idénticas para no disfrazar cambios de escala corporal. No
concluye por sí mismo si las piernas se mueven bien: requiere inspección
humana. El tiempo de las dos sesiones no está sincronizado por frame.

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
