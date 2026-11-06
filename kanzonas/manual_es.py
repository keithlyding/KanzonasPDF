"""The user manual in Spanish (Latin America): Help > User manual (F1) when the interface is in
Spanish (manual.manual_html() picks it).

A translation of manual.MANUAL with the same HTML: the same <h2 id="..."> chapters (ids in
English), tables, lists and links. Names from the interface are written exactly as
kanzonas/locale/es.po translates them (without the & accelerator), so the build's check that
every menu command is in the manual also works in Spanish. Keep it in step with the English.
"""

MANUAL = """
<h1>Manual del usuario de KanzonasPDF</h1>
<p>Un lector y editor de PDF gratuito. Use la lista de contenido de la izquierda o escriba en el
cuadro <b>Buscar en el manual</b> de arriba.</p>

<h2 id="audit-fixes">Protección del documento y edición segura</h2>
<p>Aplicar censuras quita cualquier trazado vectorial que toque una marca, incluso la parte de ese
trazado que queda fuera del cuadro. Al aplicarlas también se eliminan los metadatos, los archivos
adjuntos, el texto oculto y los scripts, a menos que desactive esa opción. Revise el resultado antes de compartirlo. Buscar y censurar
reemplaza el texto por [redacted] en las notas y los comentarios (se vuelven a escribir, de modo que no queda ninguna copia del
texto en su apariencia ni en sus datos privados) y quita por completo los sellos, las imágenes y
los archivos adjuntos que lo contienen, incluidos los datos privados y las apariencias de los sellos.</p>
<p>Al guardar cambios en un PDF que ya está protegido, se conserva su propia protección exactamente como estaba: la
misma contraseña de apertura, la misma contraseña de permisos y los mismos permisos, sin que se necesite ninguna contraseña. Así, un formulario
bloqueado con una contraseña de permisos que usted no conoce se puede rellenar y guardar igualmente, y sigue
bloqueado. (Solo en el caso poco frecuente de que la protección no se pueda conservar, KanzonasPDF le pide
las contraseñas originales; si la solicitud falla o se cancela, el archivo existente queda intacto).
Buscar y censurar solo examina el texto de las marcas que las personas ven (comentarios, etiquetas de sellos,
nombres y fechas), no sus colores ni sus formas, de modo que censurar una palabra como "fill" no
elimina marcas que no tienen relación con ella. Los documentos protegidos recientemente se excluyen de las copias de seguridad automáticas,
y una copia de recuperación existente se elimina cuando se agrega la protección. Cada copia de recuperación tiene
su propia identidad única, incluso en el caso de archivos con el mismo nombre.</p>
<p><b>Imprimir</b> (menú Archivo, barra de herramientas, Ctrl+P) abre la ventana de impresión de KanzonasPDF con una vista previa
de cada hoja tal como se imprimirá: elija la impresora y las copias, qué páginas (Todas, Página actual
o una lista como 1-3, 5), la orientación (Automática gira cada hoja para ajustarla a su página), el tamaño
(Ajustar al papel, o Tamaño real, que solo reduce las páginas demasiado grandes), si se imprimen las marcas
y los campos de formulario, y las <b>Marcas de corte</b> (vea Producción de impresión). <b>Configurar página…</b> define el tamaño del papel y los márgenes. Use las flechas
debajo de la vista previa para ver cada hoja. Las páginas se imprimen con la resolución de la impresora, hasta 600 ppp,
y se procesan por franjas, de modo que incluso los planos grandes se imprimen nítidos sin usar mucha memoria.
Las marcas y los campos de formulario siguen su propia opción de impresión, como en Acrobat: una hecha para verse
solo en pantalla no se imprime, y una hecha para imprimirse sin verse en pantalla sí. Mientras imprime, una
pequeña ventana indica en qué página va; <b>Cancelar</b> allí detiene el trabajo.</p>
<p>Copiar, extraer y exportar requieren el permiso de copia, y también Combinar archivos e
Insertar páginas desde archivo para cada PDF del que toman páginas: un PDF que no permite copiar se
rechaza, a menos que escriba su contraseña de permisos (de propietario) cuando se le pida. Imprimir requiere el permiso de
impresión y usa como máximo 150 ppp cuando la impresión de alta calidad está prohibida. Rellenar formularios
y agregar marcas respetan sus permisos por separado: firmar un campo de formulario o ponerle la fecha solo necesita
<b>Rellenar campos de formulario y firmar</b>, mientras que colocar una firma o la fecha en cualquier otro lugar
de la página modifica la página. Un formulario que solo tiene campos de firma vacíos no está firmado, así que se abre
para rellenarlo aunque esté protegido. Acoplar las páginas seleccionadas conserva las
etiquetas de página, los vínculos salientes (y lo que une un vínculo a su subrayado y a sus palabras) y la
calibración del dibujo. Acoplar deja como marcas las marcas de censura que aún no se han aplicado. La exportación a Excel escribe el texto del PDF como texto
literal en las celdas, incluido el texto que comienza con un signo igual. El OCR desactiva la telemetría de ONNX Runtime
antes de crear las sesiones de reconocimiento.</p>
<h2 id="start">Primeros pasos</h2>
<ul>
<li><b>Abrir un PDF:</b> Archivo &gt; Abrir (Ctrl+O), arrastre un archivo a la ventana o elija uno en
Archivo &gt; Abrir recientes. Cada archivo se abre en su propia pestaña, en la página y con el zoom con que lo dejó. Si
KanzonasPDF ya está abierto, un PDF que se abre desde el Explorador, un correo electrónico o un navegador se abre en una nueva pestaña
en él, y la ventana pasa al frente (se restaura si estaba minimizada). Abrir un archivo que
ya está abierto cambia a su pestaña; si el archivo cambió en el disco desde que se abrió, la pestaña
lo muestra tal como está ahora (y pregunta antes si la pestaña tiene cambios sin guardar).</li>
<li><b>Crear un PDF nuevo:</b> Archivo &gt; <b>Nuevo PDF...</b> (Ctrl+N, o pestaña Páginas &gt; Nuevo PDF)
pide el tamaño de página (Carta, Legal, Tabloide, ANSI C a E, ARCH A a E, A4 a A0) y
la orientación vertical u horizontal, y luego abre una pestaña llamada Sin título 1 con una página en blanco. Agregue páginas con
Insertar página en blanco después de la actual o Insertar páginas desde archivo (archivos PDF e imágenes), y dibuje, escriba o
firme en él como en cualquier PDF. No se guarda en ningún lugar hasta que usted lo guarda: Guardar (Ctrl+S) pregunta dónde,
como Guardar como, y al cerrarlo después de hacer cambios se le pregunta si desea guardarlo. Marque <b>No volver a
preguntar</b> para usar siempre el tamaño que eligió; cámbielo, o vuelva a hacer que se le pregunte, en
Preferencias &gt; Páginas y visualización &gt; Tamaño de página del nuevo PDF. Sin ningún documento abierto, Insertar página
en blanco crea un PDF nuevo de la misma manera, e Insertar páginas desde archivo crea un PDF nuevo, sin guardar, a partir de
los archivos que elija.</li>
<li><b>Guardar:</b> Ctrl+S. <b>Guardar como:</b> Ctrl+Shift+S. (Para una copia de archivo, vea
Guardar como PDF/A en Herramientas de documento.) Guardar como un archivo que está abierto en otra
pestaña reemplaza ese archivo y cierra esa pestaña (y pregunta antes si tiene cambios sin guardar); lo mismo ocurre
con Extraer páginas, Combinar archivos y las copias que guardan Comprimir, Sello de tiempo y la firma digital,
salvo que en ese caso la otra pestaña muestra el archivo nuevo. Deshacer es Ctrl+Z; rehacer es Ctrl+Y.
Se conservan hasta 30 pasos. Cada paso guarda solo lo que cambió la edición, así que deshacer y rehacer son rápidos
y los 30 pasos caben incluso en PDF muy grandes; el historial sigue sin superar un límite de memoria
(256 MB por documento, 512 MB para todos los documentos abiertos juntos; los pasos más antiguos se descartan primero).</li>
<li><b>Paneles:</b> Páginas/Marcadores/Capas a la izquierda (F4), Propiedades a la derecha (F6),
Lista de marcas (F7), Caja de herramientas (F8), Marcadores (F9), Vista dividida (F10). Los paneles que tenía abiertos
al cerrar KanzonasPDF (y sus tamaños, sus lados y cuál de Propiedades / Caja de herramientas estaba
delante) vuelven la próxima vez que se inicia; la Vista dividida siempre se inicia cerrada.</li>
<li><b>Un documento en su propia ventana</b> (para un segundo monitor): arrastre su pestaña hacia arriba o hacia abajo fuera
de la barra de pestañas y suéltela, o haga clic con el botón derecho en la pestaña &gt; <b>Mover a una nueva ventana</b>, o Ver &gt;
<b>Mover pestaña a una nueva ventana</b> (Ctrl+Shift+N). El documento no se vuelve a abrir: los cambios sin guardar
y el historial de deshacer se trasladan con él. Suelte una pestaña sobre las pestañas de otra ventana de KanzonasPDF (o haga clic con el botón derecho
en ella &gt; <b>Mover a la ventana</b>) para moverla allí. Cada ventana tiene sus propios paneles, herramientas y
cuadro Buscar, con la misma configuración. Cerrar la última pestaña de una ventana separada cierra esa
ventana; cerrar la ventana principal (la primera) las cierra todas, y volver a abrir los últimos
archivos al iniciar trae de vuelta los documentos de todas las ventanas, en la ventana principal. Cerrar una
ventana separada con varios documentos pregunta solo por los documentos de esa ventana. Las opciones de vista
(cuadrícula, ajuste, cuadros de comentario, resaltar campos de formulario, mostrar marcas, revisar ortografía,
tema, modo del mouse) son las mismas en todas las ventanas: al cambiar una, el menú de cada ventana la sigue.</li>
<li><b>Cerrar KanzonasPDF:</b> con un documento abierto, se le pide que lo guarde si tiene
cambios sin guardar. Con varios documentos abiertos se le hace una sola pregunta: enumera los que tienen
cambios sin guardar y ofrece <b>Guardar todo</b>, <b>No guardar</b> o <b>Cancelar</b> (Cancelar mantiene
todo abierto); cuando ninguno tiene cambios sin guardar, pregunta "¿Cerrarlos todos y salir?" (desactive esa pregunta
en Preferencias &gt; Inicio y apertura &gt; <b>Preguntar antes de cerrar KanzonasPDF con varios documentos
abiertos</b>). Cerrar una pestaña solo pregunta por ese documento.</li>
<li><b>Cinta:</b> los comandos se agrupan en pestañas: Inicio, Marcas, Medir, Organizar, Revisar,
Proteger, Formularios, Páginas, Imprimir y Ver. La pestaña <b>Marcas</b> solo tiene marcas: comentarios, notas, cuadros
de texto, llamadas, sellos, leyendas, formas e iconos de archivos adjuntos. Las marcas siguen siendo editables en cualquier visor
de PDF (Adobe Reader, navegadores) hasta que las acopla. Todo lo demás que agregue (imágenes,
Agregar texto, firmas, iniciales, fechas) se escribe en la propia página, de modo que en un visor
se ve y se comporta como acoplado; Editar texto y Editar objetos (pestaña Inicio) siguen pudiendo cambiarlo aquí, como
pueden hacerlo Acrobat y PDF-XChange. Abrir, guardar, imprimir, deshacer y rehacer están a la izquierda de las pestañas, y el
cuadro Buscar (con su número de coincidencias y sus flechas arriba / abajo) está a su derecha. La barra inferior (barra de estado, abajo a la derecha) tiene la navegación de páginas (primera,
anterior, número de página, siguiente, última página), Ajustar página, Ajustar al ancho, Tamaño real, un control deslizante de zoom y el
cuadro de zoom con alejar / acercar, como PDF-XChange Editor, y la escala del dibujo de la página actual (en rojo cuando no
tiene ninguna; haga clic en ella para establecerla). Un mensaje de la barra inferior demasiado largo para el espacio a la
izquierda de los controles de página termina en «...»; pase el mouse sobre él para leerlo entero. La cinta es compacta: dos filas de
botones, y cada pestaña cabe en una pantalla de 1366 píxeles de ancho, en inglés y en español. Los comandos que se usan
menos comparten un botón con una flecha al lado: haga clic en el botón para el comando que muestra, o en la flecha para
los demás (el botón muestra luego el último usado). En la pestaña Inicio, la flecha de Resaltado tiene Subrayado y
Tachado, y la de Firmar tiene Iniciales; en la pestaña Páginas, la de Encabezado y pie tiene Marca de agua y Fondo, y la
de Extraer tiene Reemplazar. Otros están en la lista de la flecha estrecha al final de un grupo: Configuración de
cuadrícula junto a los interruptores de ajuste, Subir y Bajar en el grupo Ordenar de la pestaña Páginas, Archivos
adjuntos y Referencias a planos en su grupo Documento, Contraer y Nombres de grupo en el grupo Cinta de la
pestaña Ver, Alinear en el grupo Modificar de la pestaña CAD. En la pestaña Inicio, Alejar y Acercar son iconos debajo
de Tamaño real. Si la ventana es demasiado estrecha para una pestaña, desplácela lateralmente con la rueda del mouse o
con la barra delgada que hay debajo. Ver &gt; <b>Mostrar nombres de grupo en la cinta</b> agrega un nombre debajo de cada grupo de
botones (la cinta queda un poco más alta, como en Microsoft Office). Ver &gt; <b>Mostrar barra de menús</b> (Ctrl+Shift+M)
oculta o muestra la barra de menús Archivo, Editar, Ver...; cuando está oculta, el botón &#9776; a la derecha
de las pestañas de la cinta tiene todos los menús, y todos los métodos abreviados de teclado siguen funcionando. <b>Contraer cinta</b>
(Ctrl+F1, o doble clic en una pestaña) muestra solo los nombres de las pestañas; haga clic en una pestaña para abrirla de nuevo. Desmarque
Ver &gt; <b>Cinta (en lugar de barras de herramientas)</b> para usar las barras de herramientas compactas clásicas (el zoom, el número de página
y Buscar vuelven entonces a la barra de herramientas superior). Los menús siempre tienen todos los comandos.</li>
<li><b>Franja de paneles:</b> los iconos del borde izquierdo abren los paneles Páginas, Marcadores, Capas y
Objetos; haga clic de nuevo en el icono iluminado para plegar el panel y tener más espacio para la página.
Los iconos de Lista de marcas y Archivos adjuntos también están allí. Ver &gt; <b>Mostrar franja de paneles (borde
izquierdo)</b> oculta la franja; los paneles muestran entonces sus nombres como pestañas en la parte inferior.</li>
<li><b>Paleta de comandos</b> (Ctrl+Shift+P; menú Ayuda, pestaña Ver): escriba algunas letras de lo que
quiere hacer y elija el comando en la lista; Enter lo ejecuta. Todos los comandos de menú y todas las herramientas están
allí con su menú y su método abreviado, así que no hay que buscar nada en la cinta. Las letras
solo tienen que aparecer en orden ("gd com" encuentra Guardar como, "gir izq" encuentra Girar página a la izquierda), y los
comandos que ejecutó desde la paleta últimamente aparecen primero.</li>
<li><b>Modo nocturno (líneas blancas sobre negro)</b> (F12; menú Ver, pestaña Ver, Preferencias &gt; Páginas
y visualización): dibuja las páginas como una pantalla de CAD. La luminosidad se invierte y los colores se conservan, de modo que
las líneas y el texto negros se vuelven blancos sobre una hoja negra, mientras que una línea roja sigue siendo roja y un resaltado
amarillo sigue siendo amarillo. Las imágenes y los escaneos también se invierten, como un negativo. Solo cambia la pantalla:
la impresión, la exportación, Capturar área y el archivo guardado son los mismos de siempre. Su elección
se recuerda.</li>
<li><b>Mejorar líneas finas</b> (menú Ver, Preferencias &gt; Páginas y visualización; activado de forma predeterminada):
cada línea se dibuja con al menos un píxel de pantalla de ancho, como la opción del mismo nombre de Acrobat. Los dibujos de
CAD usan líneas muy finas (una décima de punto o menos); con su ancho real cubren solo
parte de un píxel de pantalla al alejar y se ven de un gris pálido. Con esta opción activada siguen oscuras y
legibles con cualquier zoom. Solo cambia la pantalla: la impresión, la exportación, el OCR, Comparar y el archivo
guardado usan los anchos de línea reales. Su elección se recuerda.</li>
<li><b>Tema:</b> Ver &gt; Tema (Igual que Windows, o Igual que el sistema en Linux y macOS; Claro, Oscuro). Ver &gt; Mostrar etiquetas de texto en las
barras de herramientas agrega nombres debajo de los iconos. Coloque el puntero sobre cualquier botón o cuadro de la barra de herramientas o de la cinta para ver una información sobre herramientas
que indica qué hace y su método abreviado de teclado (el que haya establecido en Métodos abreviados de teclado);
un botón que agrupa varias herramientas (Formas, Medir) nombra la herramienta que muestra y su tecla. En la
pestaña CAD indica las letras que se escriben en la línea de comandos (Mover: escriba M y presione Enter).</li>
</ul>

<h2 id="free">Gratuito</h2>
<p>Las versiones oficiales de KanzonasPDF siguen siendo gratuitas para uso personal y comercial: sin suscripciones, sin vencimiento de prueba, sin niveles de funciones de pago, sin cuenta obligatoria ni servicio en la nube de pago obligatorio. Las donaciones opcionales nunca desbloquean funciones. El código fuente está disponible bajo la licencia GNU AGPL-3.0.</p>

<h2 id="install">Instalar, actualizar y desinstalar</h2>
<ul>
<li>Ejecute <b>KanzonasPDF-v&lt;versión&gt;-setup.exe</b> (el instalador tiene un icono azul; el programa en sí es rojo). No se necesitan derechos de administrador: se
instala para su cuenta de Windows (elija "todos los usuarios" en la primera página si es administrador y
lo desea así). Agrega un acceso directo en el menú Inicio, opcionalmente un acceso directo en el escritorio, y ofrece
KanzonasPDF como aplicación para abrir archivos PDF.</li>
<li><b>Convertirla en su aplicación predeterminada para PDF:</b> Windows no permite que los instaladores lo hagan sin preguntar. Haga clic con el botón derecho en
cualquier PDF &gt; Abrir con &gt; Elegir otra aplicación &gt; KanzonasPDF, y marque "Usar siempre esta aplicación".</li>
<li>Abrir otro PDF mientras KanzonasPDF se está ejecutando lo abre en una nueva pestaña de la misma ventana.</li>
<li><b>Actualizar:</b> use <b>Actualizar ahora</b> en el aviso de actualización o en Ayuda &gt; Buscar
actualizaciones. KanzonasPDF descarga el nuevo instalador solo desde GitHub y solo lo ejecuta cuando el
sha256 del archivo coincide con el resumen publicado con esa versión; pide guardar los documentos abiertos,
se cierra, instala la nueva versión sobre esta (para usted, o para todos los usuarios con el aviso de
administrador de Windows si así se instaló) y se vuelve a iniciar. También puede ejecutar usted mismo el
instalador más reciente sobre el anterior; no hace falta desinstalar primero. De cualquier forma se instala
en el mismo lugar y conserva su configuración, sus firmas, sus sellos y su caja de herramientas. <b>Desinstalar:</b> Configuración de Windows &gt; Aplicaciones, o el desinstalador de la carpeta de instalación.</li>
<li><b>Versión portátil</b> (<b>KanzonasPDF-portable.zip</b>): no requiere instalación. Descomprima la carpeta KanzonasPDF
en cualquier lugar (una memoria USB, una unidad de red, su carpeta Documentos) y ejecute KanzonasPDF.exe. Gracias al
archivo portable.txt que contiene, su configuración, sus firmas, sus imágenes de sellos y su certificado se guardan en una
carpeta <b>data</b> junto al programa en lugar de en el registro y las carpetas de usuario del equipo, de modo que
viajan con la carpeta. El título de la ventana y Ayuda &gt; Acerca de indican <b>(portátil)</b> cuando
esta copia se ejecuta en modo portátil. Mantenga toda la carpeta junta. La descarga tiene el mismo nombre en todas las versiones
(KanzonasPDF-portable.zip, con una carpeta KanzonasPDF dentro), así que la ruta del programa nunca tiene que
cambiar. <b>Para actualizar</b>, use <b>Actualizar ahora</b> en el aviso de actualización o en Ayuda &gt; Buscar
actualizaciones: KanzonasPDF descarga el nuevo zip portátil solo desde GitHub, y solo lo instala
cuando el sha256 del archivo coincide con el resumen publicado con esa versión. Pide guardar los documentos
abiertos, se cierra, reemplaza sus archivos de programa en la misma carpeta y se vuelve a iniciar. También puede hacerlo a mano: cierre
KanzonasPDF y descomprima la nueva descarga sobre la misma carpeta, reemplazando los archivos. Su carpeta data se conserva y, si convirtió KanzonasPDF.exe en su aplicación predeterminada para PDF
(Configuración de Windows &gt; Aplicaciones &gt; Aplicaciones predeterminadas), sigue siendo la predeterminada. Sugerencia: si Extraer todo de
Windows sugiere un nombre de carpeta nuevo, cámbielo por la carpeta que ya usa.
(Abrir un archivo adjunto sigue usando la carpeta temporal de Windows).</li>
<li><b>Versión de PortableApps.com</b> (KanzonasPDF Portable, para la plataforma PortableApps.com):
su configuración y sus archivos se guardan en la carpeta <b>Data</b> del paquete, y la plataforma PortableApps.com
la actualiza, de modo que KanzonasPDF no busca actualizaciones ni ofrece Actualizar ahora a menos que
vuelva a activar Ayuda &gt; Buscar actualizaciones automáticamente. Ambas versiones portátiles siguen a su memoria
USB a una nueva letra de unidad: si Abrir recientes muestra E:\\Docs\\plan.pdf y la memoria ahora es F:,
abre F:\\Docs\\plan.pdf.</li>
<li><b>Ayuda &gt; Buscar actualizaciones:</b> pregunta a GitHub si se ha publicado una versión más reciente de KanzonasPDF.
Un cuadro le indica la respuesta. Si hay una versión más reciente, muestra las <b>novedades desde su versión</b>: las
notas breves de cada versión más reciente que la suya, de la más nueva a la más antigua (en español cuando KanzonasPDF
está en español); <b>Descargar</b> abre la página de la versión en su navegador y <b>Actualizar ahora</b> actualiza esta
copia en el mismo lugar (vea más arriba; no en la versión de PortableApps.com, que su plataforma actualiza). La búsqueda
automática, en cambio, muestra un aviso en la parte inferior de la ventana con <b>Novedades</b> (las mismas notas),
<b>Actualizar ahora</b>, <b>Descargar</b>, <b>Omitir esta versión</b> y <b>Más tarde</b>. No se descarga ni se instala
nada hasta que hace clic en un botón.
Con Ayuda &gt; <b>Buscar actualizaciones automáticamente</b> marcado (el valor predeterminado), la aplicación busca
discretamente una vez al día: unos segundos después de iniciarse, y otra vez cada día mientras sigue abierta. Cuando no hay
nada más reciente, la barra de estado lo dice durante unos segundos ("Actualizaciones comprobadas: Tiene la última
versión"). Desmárquelo para no contactar nunca con GitHub. Si su red bloquea GitHub, la búsqueda automática simplemente
no encuentra nada.</li>
<li><b>Ayuda &gt; Informar un problema o sugerir una idea...</b> abre la página de KanzonasPDF en GitHub en
su navegador, con formularios para informar un error o proponer una idea (se necesita una cuenta gratuita de GitHub para enviar
uno). Describa lo que hizo y lo que ocurrió; por favor, no adjunte archivos PDF confidenciales. Los problemas de
seguridad (censura, contraseñas, firmas) tienen allí su propio formulario privado.</li>
<li>La descarga <b>KanzonasPDF-windows.zip</b> es el mismo programa sin el archivo portable.txt: se ejecuta
desde cualquier carpeta, pero guarda la configuración en el equipo, como la versión instalada.</li>
</ul>

<h2 id="linux">KanzonasPDF en Linux</h2>
<ul>
<li><b>Instalar:</b> descargue <b>KanzonasPDF-x86_64.AppImage</b> de la página Releases, hágalo ejecutable (clic derecho &gt; Propiedades &gt; Permisos &gt; Permitir ejecutar el archivo como programa, o <code>chmod +x KanzonasPDF-x86_64.AppImage</code>) y haga doble clic en él. No necesita instalación ni permisos de administrador. Si no se abre y menciona FUSE o libfuse.so.2, instale FUSE 2 (Ubuntu 22.04 y Debian 12: <code>sudo apt install libfuse2</code>; Ubuntu 24.04 y posteriores: <code>sudo apt install libfuse2t64</code>; Fedora: <code>sudo dnf install fuse-libs</code>) o ábralo con <code>--appimage-extract-and-run</code>.</li>
<li><b>Menú de aplicaciones y aplicación predeterminada para PDF:</b> Archivo &gt; Preferencias &gt; General &gt; <b>Agregar KanzonasPDF al menú de aplicaciones y abrir los PDF con él</b> agrega una entrada de menú y un icono solo para su usuario (en ~/.local/share) y hace que KanzonasPDF abra los archivos PDF. Desmárquelo para quitarlos de nuevo; la aplicación que abría los PDF antes vuelve a ser la predeterminada. Si usted había creado una entrada de menú llamada kanzonaspdf.desktop, se aparta mientras está la de KanzonasPDF y vuelve cuando desmarca la opción. Algunos escritorios muestran la nueva entrada solo después de cerrar sesión y volver a iniciarla. Si mueve la AppImage, ábrala una vez desde su nuevo lugar y la entrada del menú la sigue.</li>
<li><b>Actualizar:</b> <b>Actualizar ahora</b> (en el aviso de actualización o en Ayuda &gt; Buscar actualizaciones) descarga la nueva AppImage solo desde GitHub, comprueba que su sha256 coincida con el publicado con la versión, la pone en lugar del archivo anterior (mismo nombre y lugar, así que la entrada del menú y la aplicación predeterminada siguen funcionando), le pide que guarde los documentos abiertos, se cierra y abre la nueva versión. Si deja un documento abierto, la nueva versión se abrirá la próxima vez que abra KanzonasPDF. Si la AppImage está en una carpeta que usted no puede cambiar, se abre la página de la versión: descargue el nuevo archivo y reemplace el anterior usted mismo. Si inicia la AppImage con --appimage-extract-and-run, la nueva versión se inicia de la misma manera. Ejecutado desde el código fuente, KanzonasPDF solo avisa de las nuevas versiones.</li>
<li><b>Sus archivos:</b> la configuración se guarda en ~/.config/KanzonasPDF/KanzonasPDF.conf; las firmas, las imágenes de sellos, su certificado y las copias de seguridad, en ~/.local/share/KanzonasPDF/KanzonasPDF (Preferencias &gt; General muestra ambos). Al cerrar sesión o apagar el equipo (o con Ctrl+C o al cerrar la terminal desde la que se inició KanzonasPDF) con cambios sin guardar se conservan copias de seguridad, que se ofrecen en el próximo inicio, como en Windows.</li>
<li><b>Fuentes:</b> Agregar texto y Editar texto usan las fuentes instaladas para fontconfig (/usr/share/fonts, ~/.local/share/fonts, ~/.fonts...): las fuentes TrueType y OpenType se incrustan (también las colecciones TrueType, .ttc, como la mayoría de las fuentes chinas, japonesas y coreanas: la primera fuente del archivo); una fuente Type 1 no, y se usa Helvetica en su lugar. Sans Serif, Serif y Monospace usan la fuente que su sistema muestra para ellas.</li>
<li><b>Diferencias con Windows:</b> la primera opción de Ver &gt; Tema es <b>Igual que el sistema</b> (el modo claro u oscuro del escritorio); la firma digital usa su certificado personal o un archivo .pfx/.p12 (no hay almacén de certificados de Windows); para imprimir hace falta una impresora configurada en el sistema (CUPS); las ventanas Abrir y Guardar son las del escritorio o las de Qt.</li>
<li><b>Quitar:</b> desmarque la opción de Preferencias de arriba y luego elimine la AppImage. Para quitar también su configuración y sus archivos, elimine ~/.config/KanzonasPDF y ~/.local/share/KanzonasPDF.</li>
</ul>

<h2 id="macos">KanzonasPDF en macOS</h2>
<ul>
<li><b>Instalar:</b> en la página Releases, descargue <b>KanzonasPDF-macos-arm64.dmg</b>. Es para Mac con Apple silicon (M1 o posterior: menú Apple &gt; Acerca de este Mac dice Chip Apple M...) y macOS 14.4 (Sonoma) o posterior. Todavía no hay versión para Mac con procesador Intel; puede llegar más adelante si la gente la pide. Abra la imagen de disco, arrastre KanzonasPDF a la carpeta Aplicaciones que está a su lado y luego expulse la imagen de disco (abra KanzonasPDF desde Aplicaciones, no desde la imagen de disco).</li>
<li><b>La primera vez que lo abre (Abrir igualmente):</b> KanzonasPDF aún no está firmado ni notarizado por Apple, así que macOS lo detiene la primera vez y dice que Apple no pudo verificar que esté libre de malware. Cierre el aviso con <b>OK</b> o <b>Aceptar</b> (no con Trasladar a la Papelera). Luego abra Ajustes del Sistema &gt; <b>Privacidad y seguridad</b>, desplácese hasta Seguridad, donde dice que se bloqueó KanzonasPDF, haga clic en <b>Abrir igualmente</b>, confirme con su contraseña o Touch ID y vuelva a hacer clic en <b>Abrir igualmente</b>. Después se abre como cualquier otra aplicación. macOS vuelve a preguntar después de instalar una nueva versión. Hágalo solo con una imagen de disco de la página Releases de este proyecto; puede comprobarla antes en Terminal con <code>shasum -a 256 KanzonasPDF-macos-arm64.dmg</code>: el resultado debe coincidir con la línea del archivo en SHA256SUMS.txt de la versión.</li>
<li><b>Abrir archivos PDF:</b> haga doble clic en un PDF, use Abrir con en el Finder, arrastre archivos PDF a KanzonasPDF en el Dock o use Archivo &gt; Abrir. Un PDF abierto mientras KanzonasPDF se ejecuta se abre como una nueva pestaña en la misma ventana. Para abrir todos los PDF con él: seleccione un PDF en el Finder, elija Archivo &gt; Obtener información, escoja KanzonasPDF en Abrir con y haga clic en <b>Cambiar todo...</b>.</li>
<li><b>Teclas:</b> donde este manual dice Ctrl, pulse Comando (&#8984;), y donde dice Alt, pulse Opción (&#8997;): Ctrl+S es Comando-S, Ctrl+clic es Comando-clic, Alt+clic es Opción-clic, Ctrl+rueda es Comando con la rueda del ratón. Los menús, la información sobre herramientas y la tabla de métodos abreviados de teclado de este manual muestran las teclas del Mac. Acerca de, Preferencias (Comando-K) y <b>Salir</b> (Comando-Q, que cierra todas las ventanas y pregunta por los cambios sin guardar) están en el menú KanzonasPDF, a la izquierda de Archivo. Reemplazar texto es Comando-Opción-F (Comando-H oculta la aplicación en un Mac). Para las teclas de función (F1 este manual, F11 modo CAD, F12 modo nocturno...) mantenga pulsada fn en la mayoría de los teclados de Mac; si macOS usa una tecla para sí mismo, cámbiela en Ver &gt; Métodos abreviados de teclado o en Ajustes del Sistema &gt; Teclado. La tecla Eliminar (&#9003;) elimina lo seleccionado.</li>
<li><b>Actualizar:</b> KanzonasPDF le avisa cuando hay una nueva versión (Ayuda &gt; Buscar actualizaciones); en un Mac no se reemplaza a sí mismo. <b>Descargar</b> abre la página de la versión: descargue la nueva imagen de disco, arrastre KanzonasPDF a Aplicaciones y elija Reemplazar. Su configuración se conserva. Si macOS detiene la nueva versión, vuelva a permitirla con Abrir igualmente (arriba).</li>
<li><b>Sus archivos:</b> la configuración se guarda en ~/Library/Preferences/com.kanzonaspdf.KanzonasPDF.plist; las firmas, las imágenes de sellos, su certificado y las copias de seguridad, en ~/Library/Application Support/KanzonasPDF/KanzonasPDF (Preferencias &gt; General muestra ambos).</li>
<li><b>Fuentes:</b> Agregar texto y Editar texto usan las fuentes de /System/Library/Fonts, /Library/Fonts y su propia carpeta ~/Library/Fonts: las fuentes TrueType y OpenType y las colecciones TrueType (.ttc: la primera fuente del archivo) se incrustan; otros tipos (.dfont, Type 1) no, y se usa Helvetica en su lugar.</li>
<li><b>Diferencias con Windows:</b> la primera opción de Ver &gt; Tema es <b>Igual que el sistema</b> (el aspecto claro u oscuro del Mac); la firma digital usa su certificado personal o un archivo .pfx/.p12 (no hay almacén de certificados de Windows y no se usa el llavero de macOS); la barra de menús está siempre en la parte superior de la pantalla, así que no se ofrece Ver &gt; Mostrar barra de menús; no hay versión portátil.</li>
<li><b>Quitar:</b> arrastre KanzonasPDF desde Aplicaciones a la Papelera. Para quitar también su configuración y sus archivos, elimine los dos lugares de arriba.</li>
</ul>

<h2 id="navigate">Desplazarse por el documento</h2>
<ul>
<li><b>Página siguiente / anterior:</b> los botones &#9664; &#9654; junto al número de página (abajo a la derecha
con la cinta, en la barra de herramientas con las barras de herramientas clásicas), las teclas de flecha derecha / izquierda
o Av Pág / Re Pág, o escriba un número de página y presione Enter. <b>Inicio</b> y <b>Fin</b> van a la primera y a la
última página. Lo mismo está en <b>Ver &gt; Ir a</b>: <b>Página siguiente</b>, <b>Página anterior</b>, <b>Primera
página</b>, <b>Última página</b> e <b>Ir a la página...</b> (Ctrl+G: el cuadro de página, listo para un número), así que
la paleta de comandos y la línea de comandos CAD también los encuentran ("página siguiente", "última página").</li>
<li><b>Acercar / Alejar:</b> Ctrl+Plus / Ctrl+Minus, Ctrl+rueda del mouse, el control deslizante de zoom o el cuadro de zoom
(escriba un porcentaje, del 10% al 6400%; 25.5 y 25,5 funcionan igual, y 1,000 es 1000%; un zoom que no es
un porcentaje entero se muestra con un decimal). Con la rueda del mouse la página sigue al instante, algo borrosa,
y se dibuja nítida en cuanto la rueda se detiene. Los planos pesados y los escaneos grandes se completan igual después de
cualquier zoom o desplazamiento, primero el centro de la ventana, así la ventana nunca los espera. Un documento muy largo no puede llegar
tan alto: todas sus páginas juntas deben caber en el tamaño máximo que Windows puede dibujar.
Ajustar al ancho (Ctrl+2), ajustar página (Ctrl+0), tamaño real (Ctrl+1). Los documentos se abren con Ajustar al ancho, en
la página donde estaba la última vez; cámbielo en Archivo &gt; Preferencias &gt; Inicio y apertura.
Ajustar al ancho y Ajustar página siguen ajustando cuando la ventana o un panel lateral cambian de tamaño, hasta que
usted elige un zoom.</li>
<li><b>Miniaturas de páginas</b> (F4) muestra u oculta el panel izquierdo.</li>
<li><b>Vínculos del PDF:</b> coloque el puntero sobre un vínculo para ver a dónde lleva. Con la herramienta <b>Mano</b>, haga clic
en él (el puntero se convierte en una mano). Con cualquier otra herramienta, en todos los modos del mouse (Estándar, Mano,
CAD), haga <b>Ctrl+clic</b> en él (al mantener Ctrl sobre un vínculo se ve una mano y adónde lleva): un clic normal
selecciona, dibuja sobre o edita aquello sobre lo que está el vínculo, de modo que trabajar con texto, imágenes o marcas con
vínculos nunca abre el vínculo por accidente. Un vínculo a una página del documento lleva a esa página. Una dirección web o
de correo electrónico pregunta primero y luego se abre en su navegador o en su programa de correo (marque <b>No volver a
preguntar</b> para omitir la pregunta a partir de entonces). Un vínculo a otro PDF lo abre en una nueva pestaña; un
vínculo a otro tipo de archivo pregunta antes de abrirlo, y solo se abren documentos, imágenes,
archivos multimedia y dibujos comunes (los vínculos que iniciarían un programa, un script o un archivo con
macros se rechazan). Los vínculos que escriben AutoCAD y otros programas de CAD al trazar un conjunto de planos
funcionan así, incluidos los vínculos a archivos cuyos nombres tienen espacios. Un vínculo a un archivo de otro equipo (un recurso compartido de red) pregunta primero, porque
abrirlo envía su inicio de sesión de Windows a ese equipo.</li>
<li><b>Convertir cualquier cosa en un vínculo:</b> selecciónela, haga clic con el botón derecho y elija <b>Agregar vínculo…</b>; luego escriba una
dirección web o de correo electrónico (www.example.com sirve; se agrega https://) o elija una página de este
documento. Funciona con <b>palabras</b> seleccionadas con la herramienta Seleccionar (solo esas palabras se vuelven
interactivas; una selección de varias líneas crea un solo vínculo), con <b>marcas</b> (sellos, cuadros de texto,
formas, imágenes, firmas) y con las <b>imágenes, formas y texto</b> propios de la página seleccionados con Editar
objetos. <b>Aspecto</b>: <b>Subrayado</b> (una línea azul delgada dibujada en la página; el valor predeterminado para
las palabras), <b>Recuadro alrededor</b> o <b>Nada</b> (el valor predeterminado para imágenes, formas y marcas; el
puntero lo sigue detectando). Las palabras, la imagen o la marca en sí no cambian.</li>
<li><b>Los vínculos permanecen con aquello sobre lo que están:</b> mueva, cambie de tamaño o gire una marca, imagen, forma
o párrafo con vínculo, o mueva una línea con vínculo con Editar texto, y el vínculo (y su subrayado) lo acompaña;
elimínelo y su vínculo también desaparece. Un vínculo recuerda sobre qué se creó, así que solo eso
lo lleva consigo: una nube o un rectángulo dibujado alrededor de palabras con vínculo no se lleva el vínculo de las palabras cuando
se mueve o se elimina. Donde los vínculos se superponen, Quitar vínculo y Editar vínculo actúan sobre el más pequeño
que está bajo el puntero (el vínculo de las palabras, no el de una nube que las rodea). Editar palabras con vínculo con Editar texto conserva su vínculo,
incluidos los vínculos que AutoCAD escribe en un conjunto de planos.</li>
<li><b>Texto de vínculo nuevo:</b> con la herramienta <b>Vínculos</b> (pestaña Inicio &gt; Insertar, menú Herramientas), haga clic en
una zona vacía del papel o arrastre un cuadro sobre ella: la opción <b>Escribir este texto en la página</b> de la ventana está marcada,
y el texto muestra la dirección a medida que la escribe; si lo prefiere, escriba sus propias palabras en su lugar ("Nuestro
sitio web"). El texto se escribe en la página, en azul y subrayado, con el tamaño de Agregar texto (o
ajustado al cuadro), y el vínculo lo cubre exactamente. Arrastre un cuadro sobre lo que ya está en la página
(un dibujo, un escaneo) para que esa zona sea interactiva sin escribir nada.</li>
<li><b>Cambiar o quitar un vínculo:</b> haga clic con el botón derecho en él &gt; <b>Editar vínculo…</b> (a dónde lleva, su aspecto
y las palabras que escribió) o <b>Quitar vínculo</b> (el vínculo y su subrayado desaparecen; las palabras o la
imagen sobre las que estaba se quedan; las palabras que escribió el propio vínculo desaparecen con él). Hacer clic en un vínculo con la herramienta
Vínculos también lo abre para modificarlo, con <b>Eliminar vínculo</b>. La herramienta Vínculos muestra los vínculos de la página como
cuadros azules discontinuos. Todas las partes de un vínculo (varias líneas) cambian y desaparecen juntas. Ctrl+Z
deshace cualquiera de estas acciones. Para todo un juego de planos, <b>Vincular referencias a planos</b> (menú Páginas) crea los
vínculos por usted a partir de los números de plano.</li>
<li><b>Desplazar:</b> herramienta Mano (H; KanzonasPDF se inicia con ella en el modo del mouse Mano), las barras de desplazamiento, o <b>mantenga presionada la rueda del mouse y arrastre</b>
(funciona con cualquier herramienta). <b>Shift+rueda</b> siempre desplaza a la izquierda y a la derecha, en todos los
modos del mouse y cuando un paso de la rueda pasaría de página. Shift+Left/Right también desplaza
lateralmente.</li>
<li><b>Modo del mouse</b> (los tres primeros botones de la pestaña Inicio, <b>Seleccionar</b>, <b>Mano</b> y <b>CAD</b>;
el menú Ver; Preferencias &gt; Mouse): tres maneras de trabajar, cada una con sus propias opciones (vea Preferencias más abajo).
<ul>
<li><b>Mouse: Estándar (flecha, la rueda desplaza)</b>: KanzonasPDF se inicia con la herramienta Seleccionar (la
flecha) y Escape vuelve a ella; la rueda desplaza y Ctrl+rueda acerca y aleja.</li>
<li><b>Mouse: Mano (arrastrar la página)</b>: se inicia con la herramienta Mano, que arrastra la página; hacer clic en
una marca con ella la selecciona. En este modo el movimiento libre de la página está activado, así que la Mano arrastra
la página a cualquier lugar, aunque quepa en la ventana. Así se inicia KanzonasPDF la primera vez.</li>
<li><b>Mouse: CAD (la rueda acerca y aleja; mantenga presionada la rueda para desplazar)</b> (F11 lo activa, y otra vez
vuelve al modo que tenía): como en AutoCAD, la rueda del mouse acerca y aleja alrededor del cursor y mantener presionada
la rueda mueve la hoja, de modo que puede recorrer un dibujo con cualquier herramienta activa. Como en Bluebeam,
mantenga presionada <b>Ctrl</b> y gire la rueda para desplazarse hacia arriba y hacia abajo. Las páginas están sobre un
lienzo abierto, el puntero es una <b>cruz</b> (excepto con la Mano), la selección funciona como en CAD y aparece la
pestaña <b>CAD</b>, al frente, con Mover, Copiar, Girar y los demás comandos CAD: vea <b>Modo CAD</b> más abajo.</li>
</ul>
Su elección se recuerda. (Antes de la versión 1.5 esto era el interruptor del mouse estilo CAD y una herramienta
predeterminada; sus elecciones se conservan.)</li>
<li><b>Movimiento libre de la página (arrastrar la página más allá de sus bordes)</b> (menú Ver, pestaña Ver de la
cinta): un lienzo abierto alrededor de las páginas, para que la herramienta Mano (o la rueda presionada) arrastre la
página a cualquier lugar, arriba, abajo y a los lados, aunque la página entera quepa en la ventana, por ejemplo después
de Ajustar página. El menú lo cambia para el modo del mouse en uso; cada modo recuerda su propio ajuste (activado en el
modo Mano, desactivado en el modo Estándar, activado en el modo CAD).</li>
<li><b>Desplazar una página por paso de la rueda</b> (menú Ver): cuando la página entera cabe en la ventana,
de arriba abajo y de lado a lado (por ejemplo, después de <b>Ajustar página</b>), cada paso de la rueda del mouse
salta a la página siguiente o anterior, centrada, en lugar de desplazarse un poco. En cuanto acerca el zoom
de modo que algún borde de la página queda fuera de la ventana, la rueda se desplaza normalmente. Mantenga presionada
<b>Shift</b> para desplazarse a la izquierda y a la derecha en lugar de pasar de página. Activado de forma predeterminada; desactívelo para un desplazamiento continuo. Cada modo del mouse recuerda su propio ajuste. (En el modo CAD la rueda acerca y aleja
en su lugar).</li>
<li><b>Buscar texto:</b> Ctrl+F; luego Enter / F3 para la coincidencia siguiente (Buscar siguiente) y Shift+Enter /
Shift+F3 para la anterior (Buscar anterior); las flechas arriba y abajo junto al cuadro Buscar hacen lo mismo. El contador junto
al cuadro muestra en qué coincidencia está y cuántas hay ("3 de 120"; "Sin coincidencias" cuando
no hay ninguna; una palabra dividida con un guion al final de una línea cuenta como una sola coincidencia). La búsqueda empieza en la página donde está y muestra la primera coincidencia en cuanto
la encuentra; en los documentos largos sigue buscando en el resto en segundo plano (el contador indica
"3 de 120+" y la barra de estado muestra cuántas páginas se han revisado) mientras usted sigue trabajando. La coincidencia
en la que está se sombrea de naranja con un marco naranja grueso que sigue siendo lo bastante grande para verlo incluso cuando
el zoom está alejado y el texto es diminuto. En la vista <b>Ajustar página</b>, cada coincidencia trae al frente su página
entera, centrada. Cambiar el texto
o editar el documento inicia una búsqueda nueva.</li>
<li><b>Reemplazar texto...</b> (menú Editar, Ctrl+H): escriba lo que desea buscar y aquello por lo que desea reemplazarlo,
marque <b>Coincidir mayúsculas y minúsculas</b> o <b>Solo palabras completas</b> si hace falta, elija <b>Todas las páginas</b> o esta
página y haga clic en <b>Reemplazar todo</b>. Cambia el texto propio del PDF (no los comentarios). Cada línea
que cambia se vuelve a escribir como lo hace Editar texto, con la fuente propia de la línea cuando esta tiene los
caracteres, y cada palabra con su propio estilo (negrita, cursiva, color...). La línea se vuelve a escribir en su sitio y no se reajusta: cuando el texto nuevo se mete en otro
texto o pasa del borde de la página, Reemplazar texto indica en qué páginas (Ctrl+Z lo deshace; Editar texto
puede reajustar el párrafo). Las páginas con marcas de censura que aún no se han aplicado se omiten (se indica cuáles).
Ctrl+Z deshace todo el reemplazo.</li>
<li><b>Vista dividida</b> (F10) muestra una segunda vista del mismo archivo, que se desplaza de forma independiente.
Es solo para mirar: haga los cambios en la vista principal.</li>
</ul>

<h2 id="cad">Modo CAD: selección y la pestaña CAD</h2>
<p>En el modo del mouse <b>CAD</b> (Ver &gt; Mouse: CAD, F11) KanzonasPDF selecciona y edita como un programa CAD.
Empieza con <b>Editar objetos</b>, que selecciona todo a la vez: las líneas, el texto y las imágenes propios del
dibujo y las marcas dibujadas encima (nubes, líneas, notas...), en una sola selección. Mover, Copiar, Girar, Escalar,
Simetría, Alinear, Matriz y Eliminar trabajan entonces sobre todo junto, y un solo Ctrl+Z lo deshace (el texto del
dibujo solo se mueve: no se copia, gira, escala ni refleja). <b>Seleccionar</b> (la pestaña CAD, o V cuando las letras
no van a la línea de comandos) selecciona del mismo modo solo sus marcas, o los caracteres del texto de la página.</p>
<ul>
<li>Haga <b>clic</b> en algo para agregarlo a la selección. <b>Shift+clic</b> lo quita. <b>Escape</b> borra toda la
selección. Hacer clic en el papel vacío conserva la selección. Una marca está encima del dibujo, así que un clic sobre ella
toma la marca. Una marca bloqueada no se toma.</li>
<li>Las <b>teclas de flecha</b> desplazan toda la selección, los objetos del dibujo y las marcas juntos. Haga clic derecho en
una marca para ver su propio menú, y en los objetos del dibujo para ver el suyo.
<b>Cambiar el tamaño:</b> una marca seleccionada muestra sus propios controladores (las esquinas y los lados de un
rectángulo, los extremos de una línea); las formas e imágenes propias del dibujo muestran controladores a su alrededor;
varios elementos (o marcas junto con objetos del dibujo) muestran un solo recuadro con controladores alrededor de todos.
Arrastre un controlador para cambiar el tamaño; una esquina conserva las proporciones (mantenga presionada Shift mientras
arrastra para cambiarlo libremente; Shift en el propio clic quita un elemento de la selección). Todo el cambio se deshace
con un solo Ctrl+Z. El texto propio del dibujo solo se mueve. <b>Doble clic</b> en un texto para editarlo: el texto propio
de la página se abre en Editar texto, el texto de una marca (un cuadro de texto, una nota, el comentario de una forma) en
su editor.
Lo seleccionado se dibuja con <b>línea discontinua</b> (trazos azules sobre blanco, así se ve incluso sobre una línea azul)
con pequeños <b>pinzamientos</b> azules en sus extremos y esquinas, como en AutoCAD.</li>
<li>Antes de hacer clic, el puntero muestra lo que tomaría un clic: sobre algo que puede tomar (una marca, o con Editar
objetos la línea, el texto o la imagen propios del dibujo) la cruz muestra un pequeño <b>cuadro de selección</b> en el
centro, como en AutoCAD, y ese elemento se <b>atenúa</b> (se dibuja más claro) mientras el puntero está encima, así ve lo
que tomarán Mover, Copiar, Simetría, Escalar y los demás comandos. Lo que ya está seleccionado no se atenúa (se dibuja con
línea discontinua), una marca bloqueada no muestra ninguno de los dos, y ninguno aparece mientras un comando pide puntos.</li>
<li><b>Clic, mover, clic</b>: haga clic en el papel vacío, mueva el puntero (el recuadro lo sigue) y vuelva a hacer
clic. De izquierda a derecha es una <b>ventana azul</b> de línea continua: toma lo que queda completamente dentro. De
derecha a izquierda es un <b>recuadro de captura verde</b> de línea discontinua: toma todo lo que toca, incluida una
línea que lo atraviese. La primera esquina se marca en cuanto hace clic, y la barra de estado pide la otra esquina. Un
clic rápido cuenta como clic aunque el mouse se haya movido un poco al presionar, y hacer clic otra vez en la primera
esquina conserva el recuadro. Escape descarta un recuadro empezado. Mantenga presionada Shift en el segundo clic para
quitar elementos en lugar de agregarlos. Un recuadro (o un lazo) también puede empezar y terminar en el <b>área gris
alrededor de la página</b>, útil cuando la hoja está cubierta. Una forma rellena o una imagen que cubre toda la hoja (un
fondo, un escaneo) cuenta aquí como papel vacío: un clic en ella empieza un recuadro, y solo una ventana alrededor de toda
la hoja la toma (una forma rellena, también un clic justo en su borde).</li>
<li><b>Mantenga presionado el botón y arrastre</b>: un <b>lazo</b> que sigue al puntero. Si al principio lo dibuja hacia
la derecha es un lazo de ventana azul (lo que queda completamente dentro); hacia la izquierda, un lazo de captura verde
(lo que toca). Shift+lazo quita elementos.</li>
<li>Con Seleccionar, un recuadro o un lazo que no toma marcas selecciona texto: los caracteres dentro de una ventana, o
los que toca un recuadro de captura (Ctrl+C los copia).</li>
<li>Mientras dibuja un recuadro o un lazo, lo que tomaría <b>brilla</b> (azul para una ventana, verde para un recuadro de
captura), así que ve lo que obtendrá antes del segundo clic o antes de soltar; una vez tomado, se dibuja con línea
discontinua y pinzamientos. En un dibujo muy grande se completa en un
momento mientras se mueve.</li>
<li>En el modo CAD arrastrar nunca mueve nada, así que nada se mueve por accidente: los controladores cuadrados de una
marca u objeto seleccionado siguen cambiando su tamaño, y <b>Mover</b> de la pestaña CAD lo mueve.</li>
<li>Preferencias &gt; Mouse activa o desactiva cada una de estas funciones (vea Preferencias).</li>
</ul>
<p>La pestaña <b>CAD</b> (y el menú CAD) solo aparece en el modo CAD. Como en AutoCAD, seleccione primero y luego
inicie un comando, o inicie primero el comando: sin nada seleccionado le pide <b>seleccionar objetos</b> (clics,
recuadros, lazos como arriba), y <b>Enter</b> (o un clic derecho) continúa con lo seleccionado. Luego responda a su
indicación en la línea de comandos: haga clic en puntos
de la página (se ajustan a los extremos de las líneas y a las esquinas como con las herramientas de dibujo; mantenga
presionada Alt para no ajustar), escriba un valor y presione Enter, o haga clic en un botón ahí. Escape (o Cancelar)
detiene un comando; el clic derecho equivale a Enter. Cada cambio se deshace con un Ctrl+Z.</p>
<p>Para que el modo CAD no necesite otra pestaña en el trabajo diario, la pestaña CAD también tiene las herramientas que más
se usan junto a sus comandos (siguen también en sus propias pestañas). Las herramientas parecidas comparten un botón, como en la
cinta de AutoCAD: haga clic en el botón para la herramienta que muestra, o en la flecha de al lado para elegir otra; el botón
muestra luego la última usada (o la herramienta activa). <b>Marcas</b>: Rectángulo (flecha: Nube, Polígono, Máscara), Círculo (flecha: Arco),
Línea (flecha: Polilínea, Curva, Lápiz), Flecha, Cuadro de texto (flecha: Llamada), Sello (flecha: Imagen, Leyenda); en el modo CAD sus atajos
de una letra escriben en la línea de comandos. <b>Medir</b>: Longitud (flecha: Longitud de polilínea, Área, Ángulo, Radio,
Perímetro, Volumen, Conteo, Calibrar cinta métrica) y, debajo, Ajustar a objetos, Ajustar a la cuadrícula y Ajustar a
la página como iconos (como en la barra de estado de AutoCAD; pase el mouse sobre uno para ver su nombre).
<b>Editar</b>: Borrar contenido, Traer al frente (flecha: Traer adelante, Enviar atrás, Enviar al fondo), Alinear a la
izquierda (flecha: las demás alineaciones, Distribuir horizontalmente y Distribuir verticalmente), Editar texto (flecha:
Agregar texto): Editar texto cambia las palabras que ya están en la página, Agregar texto escribe texto nuevo en la
página.</p>
<p><b>La línea de comandos</b>, a lo largo de la parte inferior de la ventana en el modo CAD, funciona como la de AutoCAD.
Simplemente empiece a escribir sobre el dibujo (no hace falta hacer clic antes en la línea) y presione <b>Enter</b> (la
barra espaciadora solo escribe un espacio, como en "ajustar página"):</p>
<ul>
<li>Los nombres cortos de AutoCAD: <b>M</b> Mover, <b>CO</b> o <b>CP</b> Copiar, <b>RO</b> Girar, <b>SC</b> Escalar,
<b>MI</b> Simetría, <b>E</b> Eliminar (también ERASE, DEL), <b>AL</b> Alinear, <b>AR</b> Matriz, <b>TR</b> Recortar; o el
comienzo del nombre de un comando, en inglés o en español: MOV, COP, GIR, REC...</li>
<li>Cualquier otro comando por su nombre, como lo encuentra la paleta de comandos (Ctrl+Shift+P): "rectángulo", "nube",
"ajustar página", "guardar como"... Mientras escribe, aparece sobre la línea una lista de comandos que coinciden; Arriba
y Abajo eligen en ella. Solo se ejecuta una coincidencia segura: el nombre completo del comando, o al menos tres
letras con las que empieza el nombre (o una de sus palabras) de ese único comando y de ningún otro. Los acentos y las
mayúsculas no importan. Los comandos que cierran la ventana o quitan cosas del documento (Salir, Cerrar pestaña,
Eliminar páginas, Quitar marcas de agua...) solo se ejecutan escritos completos, para que un EX suelto nunca cierre el
programa. Cualquier otra cosa no ejecuta nada: la línea indica <b>Comando desconocido</b> (o que varios comandos
coinciden) y conserva lo que escribió, para corregirlo o para elegir un comando de la lista con Arriba y Abajo y Enter.
Un ajuste que se activa escribiendo su nombre indica si ahora está activado o desactivado.</li>
<li>Enter con la línea vacía repite el último comando.</li>
<li>Mientras se dibuja un círculo (con el centro ya marcado), escriba su radio y presione Enter.</li>
<li>Mientras se ejecuta un comando, la línea indica qué hacer a continuación y toma lo que escribe: un ángulo, un factor
de escala o una elección (bastan las primeras letras del nombre de un botón: C para Conservarlos, E para
Eliminarlos).</li>
<li>Escape borra lo que escribió; sin nada escrito, cancela el comando.</li>
<li>En el modo CAD, los atajos de una sola letra de las herramientas (V para Seleccionar, H para Mano...) escriben en la
línea de comandos (Preferencias &gt; Mouse, opciones de CAD: desactive <b>Las letras escritas sobre el dibujo van a la
línea de comandos</b> para conservarlos como atajos de herramientas; entonces haga clic en la línea de comandos para
escribir un comando); los atajos con Shift y una letra (Shift+M Longitud, Shift+A Área...) siguen funcionando mientras no
haya nada escrito, los atajos con Ctrl y Alt (Ctrl+S, Ctrl+Z...) funcionan como siempre, y las herramientas están a un
nombre de distancia ("mano", "seleccionar"). Enter sigue terminando un polígono o un área que se está dibujando, y la
barra espaciadora y Enter siguen llenando el campo de formulario al que llevó Tab.</li>
</ul>
<ul>
<li><b>Mover</b>: haga clic en el punto base y luego donde va.</li>
<li><b>Copiar</b>: haga clic en el punto base y luego donde va cada copia, tantas como quiera; Enter, Escape o Listo
termina.</li>
<li><b>Girar</b>: haga clic en el punto base y luego escriba el ángulo en grados (en sentido antihorario; -90 gira en
sentido horario) y presione Enter, o haga clic en un punto: la selección gira para que el "este" apunte hacia ahí.</li>
<li><b>Escalar</b>: haga clic en el punto base y luego escriba el factor (2 = el doble de grande, 0.5 = la mitad; de 0.001
a 1000) y presione Enter, o haga clic en un punto a una longitud que conozca y luego en el punto a la longitud que tendrá.</li>
<li><b>Simetría</b>: haga clic en dos puntos del eje de simetría y luego en <b>Conservarlos</b> (una copia reflejada) o
<b>Eliminarlos</b> (los originales se reemplazan).</li>
<li><b>Eliminar</b>: elimina la selección.</li>
<li><b>Alinear</b>: haga clic en un punto de la selección y donde va, luego en un segundo punto y donde va; después en
<b>Escalar</b> (para que también coincidan los segundos puntos) o <b>No escalar</b>.</li>
<li><b>Matriz</b>: elija las filas y las columnas (hasta 50 de cada una) y luego haga clic en el punto base, donde va la
copia de la columna siguiente y donde va la copia de la fila siguiente (la dirección también cuenta). Una matriz que
crearía más de 20 000 objetos pregunta primero (un grupo cuenta cada objeto que dibuja). Una matriz grande (más de 20 copias de una selección grande) se hace como
los programas CAD hacen los bloques: la selección se guarda una sola vez en el archivo, como un grupo de dibujo, y cada
copia coloca ese grupo, así que es rápida y el archivo no crece mucho. En Editar objetos cada una de esas copias es un
grupo; Desagrupar separa una. Esto se hace solo con líneas, formas e imágenes simples que están todas bajo el mismo
recorte y en la misma capa, donde se ve exactamente igual que copiar cada objeto; todo lo demás (grupos, objetos en
capas distintas) se copia objeto por objeto, lo que tarda más. Las copias de una selección así (Copiar, la copia de
Simetría y las matrices de cualquier tamaño) se dibujan juntas encima de los originales, como los programas CAD dibujan
los objetos nuevos; una selección repartida en capas o recortes distintos deja cada copia justo encima de su original.</li>
<li><b>Recortar</b>: como en AutoCAD, primero los <b>bordes de corte</b>: las líneas seleccionadas antes de TR, o las que
seleccione cuando lo pide, y luego Enter (Enter sin nada seleccionado: todas las líneas cortan). Después haga clic en la
parte de una línea que quiere quitar: se quita hasta los bordes de corte más cercanos que la cruzan a cada lado (o hasta su
extremo, si ninguno la cruza de ese lado). Sin bordes de corte elegidos, una línea que ninguno cruza se quita entera; con
bordes de corte elegidos, una línea que no cruza ninguno se queda (lo indica). El clic elige la línea más cercana y no se ajusta; un clic justo donde se cruzan líneas lo indica
en lugar de recortar (haga clic un poco a un lado). Haga clic una y otra vez; Enter, Escape o Listo termina. Recorta las líneas y curvas propias del
dibujo (una curva recortada sigue siendo una curva, cortada exactamente donde la cruzan las líneas), las líneas que un
dibujo pinta como barras finas rellenas (como escriben todas sus líneas algunos programas CAD; las partes que quedan son
barras igual de gruesas) y las marcas de línea, flecha, polilínea, pluma, arco y curva: lo que queda de un arco es un arco
del mismo círculo, de una curva (una línea curvada) la misma curva, y una flecha conserva la punta en la parte de su
extremo (las demás partes pasan a ser líneas simples). Un círculo o una elipse se cortan donde los cruzan líneas: lo que
queda de un círculo es un arco, de una elipse una polilínea a lo largo de ella; si la cruzan menos de dos líneas, se quita
entera, como en AutoCAD. También
recorta rectángulos, polígonos y nubes, y sus propias esquinas cortan además de las líneas que los cruzan: un clic en un lado
de un rectángulo o una nube sueltos quita ese lado de esquina a esquina, y otro clic quita otro lado. Lo que queda es una sola
marca abierta que empieza y termina en el hueco: un rectángulo o polígono se vuelve una polilínea (mismo color, grosor y
opacidad; sus esquinas siguen cortando) y una nube sigue siendo una nube, con los lados que quedan tal como estaban (se mueve,
gira, refleja, cambia de estilo y se recorta como cualquier marca; otros lectores de PDF la muestran tal como está dibujada).
Una nube en forma de elipse solo se corta donde la cruzan líneas. Un clic justo en una esquina lo indica en lugar de recortar
(haga clic en el lado, un poco lejos de la esquina). Las formas rellenas (también una Máscara, pero no las barras finas
de arriba) y las imágenes no se recortan.</li>
</ul>
<p>En un dibujo grande, el modo CAD lee los trazos de la página en segundo plano mientras usted no hace nada, poco a
poco para que la ventana siempre responda, así que el primer recuadro, lazo o comando empieza enseguida; el puntero
muestra un cursor de espera mientras un comando trabaja. Un recuadro de ventana toma una curva cuando la curva tal como se
dibuja queda dentro (sus puntos de control pueden sobresalir).</p>
<p>Lo que los comandos no hacen: el texto propio del dibujo solo se mueve (Mover); copiarlo, girarlo, escalarlo o
reflejarlo lo deja donde está y lo indica (Editar texto lo cambia). Los resaltados y otras marcas de texto se quedan sobre
sus palabras, así que solo se mueven y se copian. Una imagen o un sello reflejados se siguen leyendo al derecho, y los
cuadros de texto giran en cuartos de vuelta.</p>

<h2 id="select">Seleccionar y editar marcas</h2>
<ul>
<li><b>Herramienta Seleccionar (V):</b> arrastre sobre el texto para seleccionarlo, incluso a través del espacio entre
páginas (permanece resaltado; vea Copiar, cortar y pegar más abajo). Haga clic en una marca para seleccionarla; luego arrástrela
para moverla, arrastre un controlador cuadrado para cambiar su tamaño o cambie su aspecto en el panel de propiedades.
En el modo del mouse <b>CAD</b>, Seleccionar funciona como en AutoCAD: ventanas azules y recuadros de captura verdes, un
lazo, clics que agregan a la selección, Shift para quitar, Escape para borrarla, y arrastrar no mueve nada (vea Modo
CAD).</li>
<li>Con una herramienta de dibujo activa (rectángulo, línea, llamada, ...), hacer clic en una marca existente también la
selecciona, así que no tiene que volver a la flecha (no en el modo CAD, donde una herramienta de dibujo siempre dibuja). La <b>herramienta Mano</b> funciona igual:
haga clic en una marca (un resaltado, una nota, una forma...) para seleccionarla; arrastre en cualquier otro lugar para mover la
página. Una marca convertida en vínculo abre su vínculo en su lugar cuando se hace clic en ella con la herramienta Mano, o
Ctrl+clic con cualquier otra herramienta (un clic normal con Seleccionar la selecciona). Una marca sobre un vínculo
que ya traía el PDF (un resaltado sobre una entrada de la tabla de contenido) se selecciona; haga clic en el vínculo
junto a la marca para abrirlo.</li>
<li><b>Contornos y rellenos:</b> un rectángulo, una elipse, una nube, un polígono o una medición de área
sin relleno se selecciona por su contorno (a unos pocos píxeles con cualquier zoom, o por la etiqueta
de un área), como en Bluebeam; uno con relleno, en cualquier punto de su interior. Así, con una herramienta de dibujo o de medición,
presionar dentro de una habitación delimitada con un Área o una nube dibuja allí (una Longitud a través de la
habitación, un Conteo, otra nube) en lugar de mover el contorno.</li>
<li><b>Varias marcas:</b> haga Ctrl+clic en cada una o arrastre un cuadro desde un espacio vacío con la herramienta
Seleccionar (Ctrl+arrastrar siempre dibuja un cuadro de selección). Ctrl+clic en una marca convertida en vínculo abre el
vínculo; en ese caso, arrastre un cuadro alrededor de ella. Arrastre cualquier marca seleccionada para moverlas todas;
Supr las elimina todas; los cambios en Propiedades se aplican a todas ellas.</li>
<li><b>Eliminar:</b> Supr o Retroceso, o haga clic con el botón derecho en la marca &gt; <b>Eliminar</b>.
<b>Editar el texto de un comentario:</b> haga doble clic en él, o haga clic con el botón derecho en él &gt; <b>Editar texto…</b>.
Las mediciones, los sellos, las leyendas y los marcadores de posición de firma muestran un texto generado a partir de lo que son, así que
no ofrecen Editar texto (para cambiar los valores de un sello para rellenar, haga doble clic en él); agregue una nota o un
cuadro de texto para comentarlos.
Si hace clic con el botón derecho en un texto resaltado que está seleccionado, el menú ofrece <b>Eliminar resaltado</b>.
En la Lista de marcas (F7), haga doble clic en una fila para editar su texto; haga clic con el botón derecho en una fila para
<b>Editar texto…</b> (cuando su texto se puede editar) y <b>Eliminar</b>, o presione Supr.</li>
<li><b>Mover con las teclas de flecha:</b> con marcas seleccionadas (o imágenes y formas seleccionadas con
Editar objetos), cada pulsación de una tecla de flecha las mueve 1 pt; <b>Shift+flecha</b> las mueve 10 pt y
<b>Ctrl+flecha</b> 0.1 pt, para ajustes finos. Una serie de pulsaciones se deshace con un solo Ctrl+Z. Las marcas ligadas al
texto (resaltados, subrayados, tachados) permanecen con su texto. Sin nada seleccionado, las flechas izquierda y
derecha pasan de página como siempre.</li>
<li><b>Esc</b> borra la selección. Sin nada seleccionado, Esc suelta la herramienta que esté
elegida (un sello, una forma, una medición, Recortar...) y vuelve a su herramienta predeterminada: la Mano en el modo
del mouse Mano, Seleccionar en el modo Estándar, Editar objetos en el modo CAD. Funciona incluso justo después de que
un cuadro de diálogo o un clic en la barra de herramientas se haya llevado el foco del teclado.</li>
</ul>

<h2 id="clipboard">Copiar, cortar y pegar</h2>
<ul>
<li><b>Texto:</b> con la herramienta Seleccionar, arrastre sobre el texto; la selección permanece resaltada.
Haga <b>doble clic</b> en una palabra para seleccionarla, y haga clic <b>una tercera vez</b> para seleccionar toda su línea.
El arrastre puede cruzar el espacio entre páginas, y las páginas intermedias se incluyen.
<b>Copiar</b> (Ctrl+C) lo coloca en el portapapeles, con una línea en blanco entre páginas;
<b>Cortar</b> (Ctrl+X) además quita esas letras
de la página (Deshacer las recupera); las líneas de arriba y de abajo conservan las suyas, incluso en
texto muy apretado. En una página con marcas de censura que aún no se han aplicado, Cortar deja el texto
donde está (cortar aplicaría las marcas): aplíquelas o quítelas primero. <b>Seleccionar todo el texto</b> (Ctrl+A) selecciona todo el texto
de la página. Esc o un clic en otro lugar borra la selección.</li>
<li><b>Menú contextual:</b> haga clic con el botón derecho en la página para Cortar, Copiar, Pegar, Eliminar (para las
marcas seleccionadas) y Seleccionar todo el texto. Con texto seleccionado, también ofrece Resaltar, Subrayar, Tachar,
Comentar el texto… y Marcar para censura para ese texto. Hacer clic con el botón derecho en una marca la selecciona
primero.</li>
<li><b>Marcas:</b> seleccione una o más marcas y luego Copiar o Cortar. <b>Pegar</b> (Ctrl+V) las coloca
donde está el mouse, en cualquier página o en otro documento abierto. Pegadas en una página girada de
otra manera (una página girada), se giran para que se vean como donde las copió; un cuadro de texto
se sigue leyendo derecho.</li>
<li><b>Duplicar</b> (Ctrl+D): aparecen copias de las marcas seleccionadas ligeramente desplazadas, seleccionadas
para que pueda arrastrarlas a su lugar. En la lista de páginas, Ctrl+D duplica las páginas seleccionadas.</li>
<li><b>Imágenes y texto de otros programas:</b> Pegar coloca una imagen copiada (p. ej., una captura de pantalla)
como una marca de imagen, o un texto copiado como un cuadro de texto, donde está el mouse.</li>
<li><b>Páginas:</b> desbloquee la lista de páginas (botón de bloqueo encima de las miniaturas), seleccione miniaturas
(Ctrl+clic agrega o quita una página, Shift+clic selecciona una serie de páginas) y luego haga clic con el botón derecho en cualquiera
de las páginas seleccionadas (toda la selección sigue seleccionada) o use el menú Páginas:
<b>Copiar páginas</b>, <b>Cortar páginas</b>, <b>Pegar páginas después de las seleccionadas</b>, <b>Duplicar páginas</b>
y <b>Eliminar páginas</b>. Con el foco en la lista de páginas, Ctrl+C, Ctrl+X, Ctrl+V y Ctrl+A actúan sobre
las páginas, y Supr (o Retroceso) elimina las páginas seleccionadas, después de preguntar. Las páginas
también se pueden pegar en otro documento abierto. Los vínculos de las páginas copiadas las acompañan: un vínculo a
otra página copiada lleva a su copia, y un vínculo a una página no copiada sigue funcionando en un duplicado
o al pegar en el mismo documento (en otro documento se omite).</li>
</ul>

<h2 id="markup">Marcas de texto y comentarios</h2>
<ul>
<li><b>Resaltado</b> (Ctrl+Shift+H), <b>Subrayado</b> (Ctrl+Shift+U), <b>Tachado</b>
(Ctrl+Shift+X): arrastre sobre el texto. La selección funciona letra por letra.</li>
<li><b>Comentario</b> (C): seleccione texto y escriba su comentario. El texto se marca (resaltado,
subrayado, tachado o subrayado ondulado: elíjalo en Propiedades) y el comentario se muestra en un cuadro a su lado.
Oculte los cuadros con Ver &gt; Mostrar cuadros de comentario.</li>
<li><b>Nota adhesiva</b> (N): haga clic donde debe ir y escriba.</li>
<li><b>Cuadro de texto</b> (T): arrastre un cuadro (o haga clic) y escriba. Ctrl+Enter termina la escritura. Un cuadro de texto
es un comentario (una marca): cualquiera puede moverlo, editarlo o eliminarlo en cualquier visor de PDF hasta que se
acopla. Su fuente puede ser Helvetica, Times o Courier (Propiedades > Fuente): son las fuentes que
tiene todo visor de PDF, así que el comentario se ve igual en todas partes. Para escribir texto que forme parte de
la página, use <b>Agregar texto</b> (más abajo).</li>
<li><b>Llamada</b> (K): presione en el punto que señala y arrastre hasta donde va el texto.</li>
<li><b>Nombre del autor:</b> Editar &gt; Nombre del autor de las marcas. Se registra en sus marcas y
se imprime en los sellos.</li>
<li><b>Revisar ortografía</b> (menú Editar, activado al principio): mientras escribe un comentario, un cuadro de texto, un
campo de formulario de varias líneas, o con Editar texto y Agregar texto, las palabras mal escritas se subrayan con una línea
ondulada roja (inglés estadounidense). Haga clic con el botón derecho en una para ver correcciones, o en <b>Agregar al
diccionario</b> para que deje de marcarse (sus palabras se recuerdan). Si el clic cae justo
al lado de la palabra, las correcciones son para la palabra donde está el cursor de texto. Las abreviaturas en mayúsculas
(HVAC) y los nombres con mayúsculas en medio (KanzonasPDF) no se marcan. Haga clic de nuevo en Revisar ortografía
para desactivarla.</li>
</ul>

<h2 id="review">Revisar comentarios (menú Revisar)</h2>
<ul>
<li><b>Agregar:</b> la herramienta Comentario (C) marca texto y agrega un comentario a su lado; la herramienta Nota (N)
agrega una nota adhesiva en cualquier lugar.</li>
<li><b>Comentario siguiente</b> (Alt+Down) y <b>Comentario anterior</b> (Alt+Up) recorren cada
comentario y cada marca en orden de lectura, página por página, seleccionando cada uno. La barra de estado muestra
"Marca 3 de 12". Al llegar al final vuelve al principio.</li>
<li><b>Lista de marcas</b> (F7): todas las marcas en una tabla, empezando por la página 1 (haga clic en el encabezado de una columna
para ordenar por ella); filtre, haga clic para ir a una marca, exporte a CSV (en el orden mostrado; si el
archivo no se puede escribir, por ejemplo porque está abierto en Excel, un mensaje se lo indica). Hacer clic
en una marca bloqueada lleva hasta ella sin seleccionarla, y Eliminar en la lista no la quita: desbloquéela primero.</li>
<li><b>Mostrar marcas:</b> desmárquelo para ocultar todos los comentarios y las marcas y ver la página como si no tuviera
marcas. No se elimina nada; márquelo de nuevo para que vuelvan. <b>Mostrar cuadros de comentario</b>
oculta solo los cuadros amarillos junto al texto comentado.</li>
<li><b>Eliminar comentarios:</b> los de todos, solo los suyos o solo los de una persona, en todas las páginas o en la
página actual. Deshacer los recupera.</li>
<li><b>Acoplar comentarios:</b> convierte los comentarios y las marcas en parte permanente de la página, mientras que los campos
de formulario siguen pudiendo rellenarse. (Documento &gt; Acoplar también acopla los campos de formulario). Las marcas de censura que
aún no se han aplicado nunca se acoplan: incrustadas, parecerían una censura con el
texto todavía debajo. Si hay alguna, pregunta primero: <b>Aplicarlas primero</b> (el Aplicar censuras
habitual, para todas las marcas del documento), <b>Dejarlas como marcas</b> (siguen siendo
marcas y el resto se acopla) o Cancelar. Las marcas pasan realmente
a ser dibujo de la página: ningún programa de PDF las ve ya como marcas. Los programas que editan el contenido
de la página (Editar PDF de Acrobat, Editar contenido de PDF-XChange, Editar objetos de KanzonasPDF) pueden seguir
moviendo ese dibujo, como pueden mover el resto de la página, y usted también (Editar objetos selecciona cada
marca acoplada como un grupo; Editar texto cambia su texto); acoplar no es un bloqueo (lo mismo ocurre
en Acrobat y Bluebeam). Sirve para enviar un archivo cuyas marcas todos ven e imprimen exactamente
como usted las hizo. Para que cualquier cambio posterior se pueda detectar, firme digitalmente el PDF con el bloqueo
contra cambios (certificar): los lectores de PDF que verifican las firmas (Acrobat, PDF-XChange, KanzonasPDF)
señalan entonces cualquier cambio posterior.</li>
</ul>

<h2 id="shapes">Formas, líneas y el lápiz</h2>
<ul>
<li>Rectángulo (R), Elipse (E), Círculo (O), Nube (D), Máscara, Polígono (Y), Línea (L), Flecha (A),
Polilínea (Shift+L), Arco, Curva, Lápiz (P). Las formas comparten un botón de la barra de herramientas: haga clic en su flecha para elegir otra.</li>
<li><b>Arco</b> (como el ARCO de tres puntos de AutoCAD; en la pestaña CAD bajo la flecha de Círculo): haga clic en el inicio, en
un punto por el que pasa el arco y luego en el final; el arco sigue al puntero antes del último clic. Arrastre sus tres puntos para
cambiar su forma.</li>
<li><b>Curvar una línea o flecha:</b> selecciónela y arrastre el rombo de su centro: se vuelve una curva suave que pasa por ese
punto; los extremos se quedan donde están y la punta de flecha sigue la curva. Lleve el rombo de vuelta a la línea recta para
enderezarla. La herramienta <b>Curva</b> dibuja una directamente: haga clic en el inicio, en el final y luego hasta donde se curva.</li>
<li><b>Círculo</b> (O): arrastre desde el centro hasta un punto del círculo. En el modo CAD, haga
clic en el centro y luego en un punto del círculo, o escriba el radio en la línea de comandos y
presione Enter (en la unidad de medida de la página, la que muestra Medir &gt; Establecer escala;
también vale 12'-6", y la coma decimal, 2,5; pulgadas sobre el papel si no hay escala). Crea una marca de elipse, así que
Propiedades, el borde de nube, mover y cambiar el tamaño funcionan como en una elipse.</li>
<li><b>Máscara</b>: arrastre un cuadro sobre lo que quiere ocultar; queda cubierto por un cuadro
blanco sin contorno (como la Cobertura de AutoCAD). En Propiedades puede cambiar su color de
relleno o darle un contorno (Sin borde vuelve a quitar el contorno). Oculta lo que hay debajo en pantalla y al imprimir, pero ese
contenido sigue en el archivo: use Censurar para eliminarlo de verdad.</li>
<li><b>En el modo CAD</b> las herramientas que dibujan de un punto a otro (Línea, Flecha,
Rectángulo, Elipse, Círculo, Nube, Máscara, Cuadro de texto, Llamada, Longitud, Radio, Calibrar
cinta métrica, el cuadro del Borrador, Borrar contenido, Capturar área, Recortar páginas,
Vínculos, marcadores de posición de firma, leyendas) funcionan como en AutoCAD: haga clic donde empieza,
mueva el puntero (la forma lo sigue sin mantener el botón presionado) y haga clic donde termina.
Se ajusta, y Shift funciona, igual que al arrastrar; presionar, arrastrar y soltar también sigue
funcionando. Un clic que tiembla un poco sigue siendo un clic. Esc o un clic derecho cancela la
forma que se está dibujando; acercar, alejar o desplazarse entre los dos clics no mueve su primer
punto. Un clic sobre una marca con el Borrador la sigue eliminando de inmediato, un clic sobre un
vínculo con la herramienta Vínculos lo sigue abriendo, y dos clics en el mismo lugar con Cuadro
de texto crean uno del tamaño predeterminado. Nota, Sello, Conteo e Imagen se siguen colocando
con un clic.</li>
<li><b>Polígono / polilínea:</b> haga clic en cada punto; doble clic o Enter para terminar, Retroceso para quitar el último
punto, Esc para cancelar.</li>
<li>Con una herramienta de dibujo, hacer clic en una marca existente la selecciona, y arrastrar mueve la marca o sus
puntos, sin cambiar de herramienta. <b>Shift+clic sobre una marca</b> empieza en cambio una nueva justo ahí
(para empezar una línea en el extremo de otra, por ejemplo): no se selecciona ni se mueve nada, y el
punto se ajusta al extremo o a la esquina de la marca cuando el ajuste está activado. El puntero muestra la cruz
de dibujo mientras se mantiene presionada Shift. <b>En el modo CAD</b> una herramienta de dibujo siempre dibuja, como en
AutoCAD, sin necesidad de Shift: un clic sobre una marca empieza la nueva ahí (ajustada a su extremo o esquina); seleccione
marcas con Editar objetos o Seleccionar.</li>
<li><b>Mantenga presionada Shift</b> mientras dibuja:
  <ul>
  <li>las líneas, las flechas, las mediciones y los segmentos de polilínea se ajustan a pasos de 45&deg; (horizontal,
  vertical o diagonal);</li>
  <li>los rectángulos, las elipses y las nubes se convierten en cuadrados y círculos perfectos.</li>
  </ul></li>
<li><b>Mantenga presionada Shift al cambiar el tamaño</b> desde una esquina: los cuadrados y los círculos siguen siendo perfectos, y las demás
marcas conservan sus proporciones. Shift al arrastrar el extremo de una línea la mantiene en pasos de 45&deg;.</li>
<li><b>Borrador</b> (X): haga clic en una marca para eliminarla, o arrastre un cuadro para eliminar todo lo que haya dentro.</li>
<li><b>Borrar contenido</b> (Shift+E; pestaña Inicio, menú Herramientas): como el de Bluebeam,
arrastre un cuadro para eliminar de forma permanente el contenido propio de la página que hay dentro: texto, imágenes y líneas.
Las líneas y las curvas que cruzan el borde del cuadro se cortan allí, de modo que un muro que atraviesa el cuadro
conserva sus partes exteriores. Una forma con relleno que cruza el borde (un color sólido, un patrón de sombreado o un
degradado) conserva su parte exterior y pierde lo que estaba dentro del cuadro; una que está completamente dentro se
quita. Las marcas no se tocan (para ellas use el Borrador, que elimina una marca entera). Ctrl+Z
lo deshace. A diferencia de la censura, no deja ningún cuadro negro; para información confidencial use Censurar, que
también limpia las copias ocultas (Borrar contenido conserva en el archivo el contorno de un relleno cortado, oculto).</li>
<li><b>Capturar área</b> (Shift+P; pestaña Inicio, menú Herramientas): como Snapshot de Bluebeam, arrastre un cuadro para
copiar esa zona, con las marcas incluidas. Ctrl+V en KanzonasPDF la pega como una marca de imagen del
mismo tamaño, en cualquier página o en otro documento, hecha con el contenido <b>vectorial</b> original: las líneas
y el texto se mantienen nítidos con cualquier zoom y al imprimir, y puede moverla, cambiar su tamaño y girarla como cualquier
marca de imagen. Solo se conserva lo que está dentro del cuadro (el texto, las imágenes y las líneas de fuera se
quitan de la copia; una línea que cruza el borde se conserva entera, pero solo se ve la parte interior).
La captura también se pega como imagen en Word, Excel, el correo electrónico y otros programas.</li>
</ul>

<h2 id="snap">Cuadrícula y ajuste</h2>
<ul>
<li><b>Mostrar cuadrícula</b> (menú Ver o barra de herramientas) dibuja una cuadrícula sobre la página. Solo está en pantalla:
no se guarda en el PDF ni se imprime con él.</li>
<li><b>Configuración de cuadrícula</b> (menú Ver; en la cinta, en la flecha a la derecha de los interruptores de
ajuste): el espaciado en pulgadas, milímetros o puntos, medido en
el papel, y cada cuánto se dibuja una línea más oscura. Con el zoom muy alejado, solo se muestran las líneas
más oscuras.</li>
<li><b>Ajustar a la cuadrícula:</b> los puntos que dibuja o arrastra saltan a la intersección de la cuadrícula más cercana.</li>
<li><b>Ajustar a objetos:</b> los puntos saltan a las esquinas, los puntos medios de los bordes, los centros y
los extremos de línea de las marcas cercanas, y a los extremos de línea, los puntos medios y las esquinas del propio dibujo (útil en planos de CAD).</li>
<li>Las opciones de ajuste están en el menú Ver y en la barra de herramientas, en el grupo <b>Cuadrícula y ajuste</b> de
la pestaña Ver de la cinta, en el grupo <b>Escala y ajuste</b> de la pestaña Medir y en el grupo <b>Ajuste</b> de la
pestaña Organizar, en Configuración de cuadrícula y en Preferencias &gt; Páginas y visualización.</li>
<li><b>Ajustar a la página</b>:
los puntos saltan a las esquinas de la página, a los puntos medios de sus bordes y a su centro, y sobre sus bordes,
de modo que una marca se puede alinear exactamente con el borde o con el centro de la página.</li>
<li>Un cuadrado rosa indica un ajuste a un objeto; un círculo verde, un ajuste a la página; una cruz azul, un ajuste a la cuadrícula.
Cuando hay varios activados, gana un objeto cercano, luego la página y luego la cuadrícula.</li>
<li>El ajuste funciona con formas, líneas, mediciones, polígonos, llamadas, cuadros de texto, sellos,
notas y conteos, y al mover o cambiar el tamaño de las marcas. El lápiz y las herramientas de marcas de
texto no se ajustan.</li>
<li><b>Al arrastrar una marca o una imagen</b> (también una imagen u otro elemento de la propia página, movido
con Editar objetos) se ajusta todo su cuadro: con Ajustar a la página, su borde izquierdo, su centro o su borde
derecho se alinean con el borde izquierdo, el centro o el borde derecho de la página, y su parte superior, su
centro o su parte inferior con los de la página, cada dirección por separado, y una guía verde discontinua
muestra con qué se alineó (suelte una imagen cerca del centro de la hoja y queda exactamente en el centro); con
Ajustar a objetos, una de sus esquinas, los puntos medios de sus bordes o su centro va a un punto de una marca
cercana (una marca arrastrada también a los puntos del propio dibujo; con ambos activados, el más cercano);
con Ajustar a la cuadrícula, su esquina
superior izquierda va a la cuadrícula.</li>
<li><b>Mantenga presionada Alt</b> mientras dibuja o arrastra para colocar un punto libremente, sin ajuste.</li>
</ul>

<h2 id="properties">Colores, bordes y estilos (Panel de propiedades)</h2>
<ul>
<li>Con una herramienta activa, el panel de propiedades (F6) define el <b>estilo predeterminado</b> de esa herramienta, que se guarda
para la próxima vez. Con una marca seleccionada, cambia <b>esa marca</b>.</li>
<li>Color de línea, relleno (o <b>Sin relleno</b>), <b>Sin borde</b> para cuadros y formas, color del texto,
grosor de línea, tamaño de fuente, puntas de flecha, borde de nube, opacidad.</li>
<li><b>Restablecer valores predeterminados</b> devuelve una herramienta a su estilo original.</li>
<li><b>Caja de herramientas</b> (F8, o la pestaña Ver): sus estilos de marca favoritos, a un clic de distancia. F8
o el botón lo abre y, cuando está visible, lo vuelve a cerrar (si está detrás de la pestaña
Propiedades, pasa al frente). Haga clic en una entrada y luego
dibuje: obtiene esa herramienta con ese color y ese tamaño, y la configuración normal de la herramienta se queda como
estaba. Empieza con algunas entradas listas para usar (nube de revisión roja, resaltado amarillo y verde,
flecha roja, rectángulo azul, cuadro de texto rojo, llamada amarilla, sellos APROBADO y RECHAZADO); cámbieles el nombre
o elimínelas (clic con el botón derecho). Para guardar las suyas: dibuje una marca y aplíquele un estilo, selecciónela y haga clic en
<b>Agregar</b>. <b>Más</b> &gt; Agregar las herramientas iniciales recupera las entradas listas para usar; Exportar caja de herramientas /
Importar caja de herramientas comparte un cofre con otras personas.</li>
</ul>

<h2 id="rotate">Girar marcas</h2>
<ul>
<li>Seleccione una forma y arrastre el <b>controlador redondo</b> que está encima de ella. Mantenga presionada Shift para pasos de 15&deg;.</li>
<li>O escriba un ángulo en <b>Rotación</b> en el panel de propiedades (en sentido antihorario).</li>
<li>Los cuadros de texto y las llamadas giran en pasos de 90&deg; (una limitación de los cuadros de texto de PDF).</li>
</ul>

<h2 id="arrange">Alinear, distribuir y orden de apilamiento (Organizar)</h2>
<ul>
<li>Seleccione dos o más elementos y luego use la barra de herramientas o el menú <b>Organizar</b>: Alinear a la izquierda,
Alinear al centro (horizontalmente), Alinear a la derecha, Alinear arriba, Alinear al medio (verticalmente), Alinear abajo.
Los elementos pueden ser de cualquier tipo y estar mezclados: marcas, y las líneas, formas, imágenes y texto propios de la
página seleccionados con Editar objetos o con un cuadro de selección del modo CAD. El texto de la página solo se mueve (su
cuadro conserva su tamaño). Todo el cambio se deshace con un solo Ctrl+Z.</li>
<li><b>Alinear respecto a:</b> Alinear con la primera seleccionada (el valor predeterminado), Alinear con la última seleccionada,
Alinear con toda la selección o Alinear con la página. Elíjalo en la lista desplegable de la barra de herramientas o en Organizar &gt;
Alinear respecto a. La primera marca seleccionada tiene un contorno más grueso. Cuando se seleccionan marcas y objetos
propios de la página a la vez, las marcas cuentan como seleccionadas primero.</li>
<li><b>Distribuir horizontalmente</b> / <b>Distribuir verticalmente</b> (tres o más): espacios iguales;
las dos de los extremos no se mueven.</li>
<li><b>Traer al frente</b> (Ctrl+Shift+]), <b>Traer adelante</b> (Ctrl+]),
<b>Enviar atrás</b> (Ctrl+[), <b>Enviar al fondo</b> (Ctrl+Shift+[). Con imágenes o formas de
la propia página seleccionadas (herramienta Editar objetos), estos comandos cambian, en su lugar, el orden de esos objetos en la página
(vea Editar las imágenes, formas y texto propios del PDF).</li>
</ul>

<h2 id="objects">Panel Objetos y bloqueo</h2>
<ul>
<li>Pestaña <b>Objetos</b> (panel izquierdo, junto a Páginas, Marcadores y Capas): todas las marcas de la
página actual, de delante (arriba en la lista) hacia atrás. Haga clic en una fila para seleccionar esa marca incluso
cuando está completamente tapada por otras; Ctrl/Shift+clic selecciona varias. Al frente, Subir, Bajar
y Al fondo cambian el orden de apilamiento.</li>
<li>Columna <b>Bloquear</b>, u Organizar &gt; <b>Bloquear lo seleccionado</b> (Ctrl+L): una marca bloqueada se comporta
como si fuera parte de la página. No se puede hacer clic en ella, moverla, seleccionarla ni borrarla, y arrastrar
sobre ella inicia en cambio un cuadro de selección o una marca nueva. Desmarque Bloquear (u Organizar &gt;
<b>Desbloquear todas las marcas</b>) para volver a editarla. El bloqueo es el indicador estándar "bloqueado" de PDF, así que
Acrobat y PDF-XChange también lo respetan.</li>
<li>Columna <b>Mostrar</b>: oculta una sola marca (sigue en el archivo; desmarcar Mostrar marcas en el
menú Revisar las oculta todas).</li>
<li>La última fila, <b>Contenido de la página</b>, es el propio PDF original. Su texto y su dibujo no son
objetos separados que pueda elegir (un plano de CAD puede contener más de 100,000 trozos de línea); use Editar
texto para su texto y la pestaña Capas para las capas de CAD.</li>
</ul>

<h2 id="stamps">Sellos</h2>
<ul>
<li>Herramienta Sello (M): elija un sello en Propiedades (Aprobado, Borrador, ... o escriba su propio texto)
y luego haga clic para colocarlo.</li>
<li><b>Agregar mi nombre</b> y <b>Agregar la fecha</b> son casillas separadas. Cambiarlas en un
sello ya colocado lo vuelve a dibujar (una fecha agregada de nuevo muestra la fecha de hoy).</li>
<li><b>Agregar sello de imagen…</b> agrega su propia imagen (PNG/JPG) a la lista de sellos.</li>
<li><b>Sellos para rellenar:</b> <b>Para rellenar: OC n.º / Fecha de pedido</b> y <b>Para rellenar: Solicitud n.º / Fecha
de envío</b> en la lista de sellos. Al hacer clic para colocar uno, un cuadro pide el número y la
fecha (la fecha empieza siendo la de hoy, en el formato de fecha de Preferencias &gt; Usted). Haga doble clic en uno ya
colocado para cambiar lo que dice; cambia de tamaño para ajustarse. Su texto de comentario (en la Lista de marcas, en su CSV
y en otros programas de PDF) se lee como "OC n.º OC-4471, Fecha de pedido 26/10/2026".</li>
</ul>

<h2 id="legends">Leyendas</h2>
<ul>
<li><b>Leyenda</b> (pestaña Marcas, Herramientas &gt; Leyenda; en la pestaña CAD bajo la flecha de
Sello), como en Bluebeam: haga clic donde va su esquina superior izquierda, o arrastre un cuadro
para fijar su ancho (el texto toma el tamaño que cabe). Coloca un cuadro que lista los tipos de
marcas usados: cada fila tiene una pequeña muestra dibujada con el estilo de esa marca (color,
grosor de línea, relleno, nube, punta de flecha...), su etiqueta (el nombre de la herramienta, o el
asunto de la marca cuando lo tiene, como suelen tenerlo las marcas de Bluebeam; el nombre del grupo
de un conteo; la palabra de un sello) y cuántas hay. Las marcas de un mismo tipo con estilos
distintos (nubes rojas y nubes azules) tienen una fila cada una. Las mediciones muestran además su
longitud, área o volumen total, en las unidades de la página (Medir &gt; Establecer escala).</li>
<li><b>Se actualiza sola</b> cuando se agregan, cambian o eliminan marcas, como parte del mismo
cambio: Ctrl+Z deshace la marca y la actualización de la leyenda juntas, y Rehacer vuelve a poner
ambas. Nunca se cuenta a sí misma ni a otra leyenda, ni a las marcas ocultas, las marcas de censura,
los marcadores de posición de firma, ni las respuestas y estados de revisión de un hilo de
comentarios (son parte de la marca a la que responden). Aplicar censuras la vuelve a dibujar con las marcas que
quedan (vea Censura).</li>
<li><b>Opciones</b> (panel Propiedades: elíjalas antes de colocarla, con la herramienta Leyenda
elegida, o en una leyenda seleccionada): <b>Título</b> (Leyenda al principio; vacío para ninguno),
<b>Marcas de</b> <b>Esta página</b> o <b>Todo el documento</b> (todas las páginas, con los totales
en las unidades de esta página), <b>Mostrar la cantidad</b>, <b>Mostrar los totales de las
mediciones</b>, <b>Tamaño del texto</b>, <b>Borde</b> y su color, el relleno y el color del
texto.</li>
<li>Se mueve, cambia de tamaño (el texto crece o se achica con el cuadro), se copia, se bloquea y se
deshace como cualquier marca. Es una marca de sello estándar con su propia apariencia, así que otros
programas de PDF la muestran e imprimen tal como se ve aquí, y Acoplar comentarios la vuelve parte
de la página.</li>
</ul>

<h2 id="images">Imágenes y archivos adjuntos (videos y más)</h2>
<ul>
<li>Herramienta <b>Imagen</b>: arrastre un cuadro y elija una imagen (PNG, JPEG, BMP, GIF, TIFF). Se ajusta
dentro del cuadro conservando sus proporciones; si solo hace clic, se coloca con su tamaño natural.
La imagen se incrusta en el PDF con su calidad y su tamaño de archivo originales y pasa a formar parte de
la propia página, como Agregar imagen de Acrobat: los visores de PDF no pueden moverla ni eliminarla. Muévala, cambie su tamaño,
gírela o elimínela con <b>Editar objetos</b> (Shift+O), como en Acrobat y PDF-XChange. Para una
imagen que siga siendo una marca movible, use <b>Agregar sello de imagen…</b> con la herramienta Sello. Las firmas,
las iniciales y las fechas colocadas forman parte de la página de la misma manera.</li>
<li>Herramienta <b>Adjuntar archivo</b>: haga clic donde debe ir el icono del clip y elija cualquier archivo, como
un video, una hoja de cálculo o una foto. El archivo se incrusta dentro del PDF, así que viaja con él.
<b>Haga doble clic en el icono</b> para abrir el archivo en el programa que Windows usa para él (los videos se reproducen
en su reproductor de video habitual). Adobe Acrobat, Bluebeam y PDF-XChange también pueden abrirlos.</li>
<li>Los videos no se reproducen dentro de la página: eso solo funciona en unos pocos lectores de PDF, así que adjuntar
es la forma fiable de enviar un video con un PDF. Los archivos grandes hacen que el PDF crezca otro tanto
(se le advierte por encima de 50 MB).</li>
<li><b>Archivos adjuntos</b> (menú Documento): todos los archivos adjuntos a este PDF, incluidos los que agregaron
otros programas. Abrir, Guardar como, Ir a su página o Eliminar.</li>
<li>Por su seguridad, Abrir pregunta primero y solo abre documentos, imágenes, sonido,
video y dibujos comunes (PDF, texto, Word/Excel/PowerPoint sin macros, imágenes, MP3/MP4,
DWG/DXF...). Todo lo demás, incluidos programas, scripts, páginas web y archivos de Office con
macros, no se abre: use Guardar como y ábralo usted mismo si confía en él. Las copias abiertas se
marcan como descargadas de internet, de modo que Windows y Office las tratan con la misma
precaución.</li>
</ul>

<h2 id="editobjects">Editar las imágenes, formas y texto propios del PDF</h2>
<ul>
<li>Herramienta Editar objetos (Shift+O; pestaña Inicio, menú Herramientas), como Editar contenido de Bluebeam: actúa sobre
las imágenes (logotipos, fotos, escaneos) y las formas vectoriales (líneas, rectángulos, círculos, curvas,
zonas con relleno, trazos de CAD) que forman parte de la propia página, no sobre las marcas (en el modo del mouse CAD también toma
las marcas dibujadas encima: vea Modo CAD). Coloque el puntero sobre un objeto
para verlo contorneado; haga clic para seleccionarlo. Las líneas se detectan a unos pocos píxeles; una forma con relleno
se detecta en cualquier punto de su interior.</li>
<li><b>Texto:</b> el texto propio de la página (lo que escribió Agregar texto y el texto del PDF) se selecciona
párrafo a párrafo: haga clic en una palabra para seleccionar su párrafo; todo lo que Agregar texto escribió de una
vez se selecciona junto. Un cuadro de selección toma texto solo cuando no contiene imágenes ni formas
(así, un cuadro alrededor de un detalle de un dibujo selecciona sus trazos, no sus rótulos); Ctrl+clic agrega texto
a una selección. En el modo del mouse <b>CAD</b>, la selección funciona como en AutoCAD: una ventana azul (de izquierda a
derecha) toma las líneas, el texto, las imágenes y las marcas que quedan completamente dentro, un recuadro de captura verde (de derecha
a izquierda) todo lo que toca, texto y trazos juntos; los clics, los recuadros y los lazos agregan a la selección, Shift
quita, Escape la borra, y los comandos de la pestaña CAD la cambian (vea Modo CAD). Presione <b>Supr</b> (o Retroceso) o haga clic con el botón derecho &gt; <b>Eliminar</b> para quitarlo;
arrástrelo para moverlo (los resaltados y otras marcas que tenga encima se mueven con él). Aquí el texto no se redimensiona,
no se gira ni se reordena en la pila: cambie sus palabras, su fuente y su tamaño con Editar texto. Las imágenes y las líneas
que tiene debajo se quedan. Si otro texto se superpone tanto que algunas de sus letras también desaparecerían,
KanzonasPDF pregunta primero. El texto invisible (la capa de texto reconocido de un escáner) no se selecciona.</li>
<li><b>Grupos:</b> un grupo de dibujo que la página coloca como una sola pieza (las marcas y los sellos acoplados
se convierten en esto, y algunos programas exportan un dibujo entero como uno solo) se selecciona, se mueve, se redimensiona,
se gira, se elimina y se reordena en la pila como un solo objeto, como en Acrobat y PDF-XChange. Un grupo que
ocupa toda la página no se selecciona con un clic (eso tomaría la hoja cada vez que hiciera clic en
papel en blanco): arrastre un cuadro de selección alrededor de la página para seleccionarlo.
Haga clic con el botón derecho en un grupo &gt; <b>Desagrupar</b> para separarlo: se ve igual, pero sus formas e
imágenes pasan a ser objetos separados que puede seleccionar uno por uno, y su texto se puede cambiar con
Editar texto. Un grupo que solo contiene otro grupo (como lo escriben muchos programas) se separa
de una vez; un grupo con grupos dentro sigue teniéndolos después de un Desagrupar.</li>
<li><b>Varios a la vez:</b> Ctrl+clic agrega o quita un objeto, o arrastre un cuadro desde un espacio vacío
para seleccionar todo lo que esté completamente dentro de él (Ctrl+arrastrar agrega a la selección). En los dibujos de CAD, una
"forma" suele ser muchas líneas separadas, así que un cuadro es la manera más rápida de tomarla.</li>
<li>Arrastre la selección para moverla. Las formas siguen al puntero (no son un cuadro vacío),
y la página en sí solo cambia cuando suelta el botón, así que un grupo grande se sigue arrastrando con rapidez.
Arrastre un controlador de esquina para cambiar su tamaño conservando sus proporciones
(mantenga presionada Shift para estirarla libremente), o un controlador lateral para hacerla más ancha o más alta. Cambiar el tamaño de una forma también
cambia la escala del grosor de sus líneas.</li>
<li>Supr (o Retroceso) elimina la selección. Haga clic con el botón derecho para Desagrupar (grupos), Girar en el sentido de las agujas del reloj, Girar
en sentido contrario a las agujas del reloj, los comandos de orden de apilamiento y Eliminar, y, para una sola imagen, Copiar imagen
(Ctrl+V la pega como una marca de imagen) y Guardar imagen como…. Esc anula la selección.</li>
<li><b>Orden de apilamiento:</b> cuando los objetos propios de la página se tapan entre sí, seleccione uno y use
<b>Traer al frente</b> (Ctrl+Shift+]), <b>Traer adelante</b> (Ctrl+]), <b>Enviar atrás</b>
(Ctrl+[) o <b>Enviar al fondo</b> (Ctrl+Shift+[), desde el menú contextual u Organizar. Al frente y
al fondo significan delante o detrás de todo lo que hay en la página, incluido el texto de la página; adelante y
atrás lo mueven más allá del siguiente objeto con el que se superpone. El objeto conserva sus colores, su estilo de línea y su
transparencia. Si estaba recortado por un contorno de recorte donde estaba, deja de estarlo donde
queda.</li>
<li>Solo cambian los objetos seleccionados: mover, cambiar el tamaño y girar conservan su lugar en el
orden de dibujo (el texto impreso sobre una imagen sigue encima), sus colores y sus estilos de línea, y
las imágenes no se vuelven a comprimir, así que la calidad no baja. Ctrl+Z deshace cada cambio.</li>
<li>El texto no se puede seleccionar con esta herramienta (use Editar texto), ni tampoco los objetos dentro de un objeto
agrupado (un XObject de formulario; use primero Desagrupar) ni los contornos de recorte. En los dibujos muy grandes, el primer clic en una página
tarda un momento mientras se lee la página.</li>
</ul>

<h2 id="edittext">Editar el texto propio del PDF</h2>
<ul>
<li>Herramienta <b>Agregar texto</b> (Shift+T; pestaña Inicio junto a Editar texto, menú Herramientas): haga clic donde va
el texto y escriba (Enter termina, Shift+Enter empieza una línea nueva). El texto se escribe en la propia
página, como Agregar texto de Acrobat: los visores de PDF no pueden cambiarlo, y Editar texto lo cambia más adelante.
Elija la fuente (cualquier fuente instalada, además de Negrita y Cursiva), el tamaño y el color en Propiedades. El
<b>Tamaño de fuente</b> también se puede cambiar mientras escribe: el texto se muestra en el tamaño nuevo de inmediato.
Los botones de estilo sobre el cuadro dan estilo a palabras sueltas, como en Editar texto (vea <b>Negrita, cursiva,
subrayado y color para palabras sueltas</b> más abajo). Solo se guardan en el archivo las letras que se usan.</li>
<li><b>Cambiar la fuente o el tamaño de una línea:</b> con la herramienta Editar texto, haga clic en la línea: Propiedades
muestra su propio <b>Tamaño de fuente</b>. Cambie el tamaño, o elija una fuente (y Negrita / Cursiva), y presione
Enter, cambiando el texto o no. La elección se aplica solo a esa línea: la siguiente línea en la que
haga clic vuelve a conservar su propia fuente y su propio tamaño (Mantener la fuente de la línea / Mantener el tamaño de la línea). Una fuente o un
tamaño elegidos antes de hacer clic en una línea se aplican a esa línea.</li>
<li><b>Eliminar texto:</b> con la herramienta Editar texto, haga clic con el botón derecho en el texto &gt; <b>Eliminar texto</b>, o
selecciónelo con la herramienta Editar objetos y presione Supr (vea más arriba). Desaparece todo el párrafo, todas
las líneas que Agregar texto escribió de una vez; las imágenes y las líneas que tiene debajo se quedan. Ctrl+Z lo recupera.</li>
<li><b>Editar un párrafo:</b> con la herramienta Editar texto (Ctrl+E), el contorno discontinuo bajo el
puntero muestra lo que edita un clic: un párrafo entero o una línea (mantenga presionada Alt para una línea).
Haga clic en cualquier lugar de un párrafo: el párrafo entero se abre en un cuadro de su ancho con el cursor en la palabra en la que hizo clic, y a medida que
escribe, las palabras se reajustan, como en Word. Presione Enter y el párrafo se vuelve a escribir con su fuente, su tamaño,
su color y su interlineado, y conserva su alineación (izquierda, derecha, centrada o justificada) y una
primera línea con sangría o con sangría francesa (la de un párrafo numerado). Una palabra dividida con un guion al final de una línea se vuelve a unir cuando el diccionario
conoce la palabra entera (spe-/cification); una palabra compuesta con guion (self-/consolidating) conserva su
guion. El número o la viñeta de un elemento de lista se queda donde está y su texto se vuelve a escribir.
Shift+Enter empieza un párrafo nuevo. Arrastre un controlador lateral para hacerlo más ancho o más estrecho, o el
contorno para moverlo (los vínculos que tiene encima se mueven con él; los resaltados y subrayados dibujados en la página se quedan
donde estaban, ya que las palabras se han movido dentro del párrafo). Un párrafo que se alarga crece
hacia abajo; no empuja hacia abajo lo que tiene debajo, así que si ahora se superpone a otro texto o pasa del
borde inferior de la página, la barra de estado lo indica (Ctrl+Z lo deshace). Cada palabra conserva su propio estilo
durante la edición y el reajuste: su fuente, su tamaño, la negrita, la cursiva, el color, el subrayado y el
tachado. El cuadro los muestra como en la página.</li>
<li><b>Negrita, cursiva, subrayado y color para palabras sueltas:</b> mientras edita (un párrafo, una
línea, o texto nuevo con Agregar texto), seleccione palabras y use los botones sobre el cuadro:
<b>Negrita</b> (Ctrl+B), <b>Cursiva</b> (Ctrl+I), <b>Subrayado</b> (Ctrl+U),
<b>Tachado</b>, <b>Color del texto</b>, y <b>Texto más grande</b> (Ctrl+]) / <b>Texto más
pequeño</b> (Ctrl+[), de un punto en un punto (una línea con palabras más grandes baja lo que
necesitan, para que no se monten sobre la de arriba). Presione de nuevo un botón para quitar el estilo. Sin nada
seleccionado, el botón fija el estilo de lo que escriba a continuación. El texto escrito junto a una palabra toma
el estilo de esa palabra; el texto escrito en un cuadro vacío toma el estilo principal del párrafo.
<br>La negrita y la cursiva conservan la fuente de la línea. Se usa la negrita o la cursiva real de la misma familia
cuando está incrustada en el PDF o instalada en esta computadora (Arial Bold para Arial, Times New Roman Italic
para Times New Roman...); cuando ninguno la tiene, la misma fuente se dibuja más gruesa (negrita) o
inclinada (cursiva), como hace Word con una fuente sin negrita ni cursiva. Solo los caracteres que la fuente
no puede escribir de ningún modo pasan a otra fuente, palabra por palabra. Quitar la negrita a una palabra escrita en una
fuente negrita requiere el estilo normal de esa fuente (incrustado o instalado); sin él la palabra sigue
en negrita.
<br>Los subrayados y las líneas de tachado se dibujan en la página en el color de las palabras, una línea
por cada línea de texto, y se mueven y se reajustan con sus palabras cuando se vuelve a editar el párrafo. Una
línea fina dibujada justo debajo (o a través) de una serie de palabras y tan larga como ellas, como escribe los subrayados
la exportación a PDF de Word, se lee como su subrayado; una línea más larga, el borde de una tabla o
la raya de un cuadro de rótulo se quedan donde están.</li>
<li><b>Qué cuenta como párrafo:</b> líneas de un mismo tamaño, una debajo de otra con un interlineado
uniforme, alineadas por un lado (o centradas), que se ajustan como texto continuo. Termina en su
última línea corta, de modo que los pasos numerados y los párrafos sin espacio entre ellos son cada uno
independientes; una línea que empieza con un número o una viñeta ("2.", "(b)", "1.Turn", una viñeta con símbolo)
empieza uno nuevo. Todo lo demás se
edita línea por línea: las líneas sueltas; los rótulos de dibujos, los cuadros de rótulo y el texto de las cotas; las celdas de tablas
y cuadros; una columna junto a otra columna; un título (su tamaño es distinto del texto
que tiene debajo); los elementos de lista, cada uno por separado (también una lista de elementos de una línea cuyas viñetas están
dibujadas, donde cada línea es una oración independiente); el texto escaneado y el texto de lado, y las páginas
giradas.</li>
<li><b>Editar una línea:</b> haga <b>Alt+clic</b> en una línea para editar solo esa línea, incluso dentro de un
párrafo. <b>Presione sobre una línea y arrastre</b> para moverla (su texto y su fuente se quedan como están,
también el estilo y el subrayado de cada palabra).
Al editar una línea, el cursor va donde
hizo clic, y la línea recibe un contorno discontinuo con controladores, como un objeto seleccionado. Escriba el
cambio; arrastre el contorno para mover el texto, o arrastre un controlador para cambiar el ancho al que se ajusta
el texto (las letras conservan su tamaño). Presione Enter (o haga clic en otro lugar)
para terminar, Shift+Enter para empezar una línea nueva, Esc para cancelar. Guardar, cerrar el documento,
Deshacer o un cambio de página también terminan una edición en curso, así que el texto escrito nunca se pierde.
El texto de lado (girado en la página, o en una página girada) se abre en un cuadro vertical sobre el
centro de la línea para que sea fácil escribir, con el cursor donde hizo clic a lo largo de la línea; el texto
sigue girado en la página cuando termina.</li>
<li>Los resaltados, subrayados, tachados, comentarios y notas adhesivas de esa línea se mueven con ella.</li>
<li>Las palabras que la página dibuja invisibles (las palabras de una capa de OCR en una línea, una palabra
oculta) siguen invisibles cuando su línea o su párrafo se edita, se arrastra, se cambia con Reemplazar texto o
se mueve con un dibujo; el cuadro las muestra tenues. Las palabras semitransparentes conservan su opacidad.</li>
<li>Se usa la fuente original cuando está incrustada o instalada y tiene todos los caracteres que
escribió; si no, la fuente estándar más parecida o, para los caracteres que estas no pueden escribir (griego como
&Omega; &Delta;, símbolos, chino y otras escrituras), una fuente Unicode integrada. Solo se guardan las letras
que se usan, así que los archivos siguen siendo pequeños. La barra de estado le indica qué fuente se usó. Si ninguna
fuente tiene un símbolo que escribió o que venía del PDF (un signo menos, un signo de diámetro, un
espacio estrecho invisible...), se prueba una fuente instalada más amplia como Segoe UI, y luego se usa un carácter parecido
(- para el signo menos, &Oslash; para el signo de diámetro, un espacio normal para uno
invisible). Los caracteres que no se pueden escribir de ninguna manera, como los emojis, se indican en un mensaje, y
no se cambia nada. El texto que se escribe de derecha a izquierda (hebreo, árabe) todavía no
se puede editar, mover ni añadir (saldría en el orden equivocado): un mensaje lo dice, y no se
cambia nada. Una línea de una
página que todavía tiene marcas de censura sin aplicar no se puede editar hasta que las aplique o las quite.</li>
<li><b>Páginas escaneadas</b> (una imagen del papel con texto reconocido encima, del OCR de su
escáner o de Reconocer texto): Editar texto, Buscar y reemplazar y mover una línea también cambian la
imagen. Las palabras antiguas se cubren con el color del papel, y el texto nuevo se escribe
de modo que coincida con el escaneo: KanzonasPDF dibuja las palabras antiguas en cada fuente estándar y en las fuentes
instaladas habituales (Arial, Calibri, Times New Roman, Courier New y otras), normal, negrita y
cursiva, las compara con las letras escaneadas y usa la más parecida, con el tamaño y sobre
la línea base que encajan, en el color de tinta del escaneo (gris, azul...). El editor se abre con esa fuente
y ese tamaño, y la barra de estado indica con qué se igualó ("Se igualó el escaneo: Helvetica Bold,
11 pt"). Una fuente o un tamaño elegidos en Propiedades siguen teniendo prioridad. Las líneas de formulario bajo el texto y
el texto de las líneas de arriba y de abajo se quedan como están, y una casilla de verificación con la que empieza el texto del escaneo
se queda en la imagen mientras el texto nuevo siga empezando con ella. El
tipo de letra escaneado no se puede identificar a partir de una imagen, así que el resultado es la fuente disponible más parecida;
si el texto reconocido no coincide con las letras (el OCR las leyó mal), se usa Helvetica con
el tamaño de las letras, y la barra de estado lo indica. La línea nueva es texto real: la búsqueda, la copia y Editar
texto funcionan con ella, y editarla de nuevo conserva su fuente.</li>
</ul>

<h2 id="measure">Medir</h2>
<ul>
<li>Primero defina la escala del dibujo: Medir &gt; <b>Establecer escala</b> (escalas predefinidas como 1/4" = 1'-0",
1:100), o <b>Calibrar cinta métrica</b> (Calibrar en la cinta): arrastre a lo largo de una dimensión conocida y escriba su longitud
real. KanzonasPDF lee las notas de escala escritas en el plano (SCALE: 1/4" = 1'-0", 1" = 20',
1:50, NTS, en el cuadro de rótulo o debajo de los títulos de los detalles): Establecer escala las ofrece como <b>Escala
escrita en el plano</b>, que queda elegida automáticamente cuando el cuadro de rótulo tiene una, y la barra de estado
menciona lo que dice el plano mientras no haya ninguna escala definida. La escala de una página va con ella:
las copias hechas con Duplicar páginas, Copiar páginas y Pegar, Extraer páginas, Insertar páginas desde archivo y
Combinar archivos la conservan.</li>
<li>La escala de la página actual está siempre a la vista: en letra grande debajo de "Establecer escala" en el
grupo <b>Escala de la página</b> de la pestaña Medir (1/4" = 1'-0", 1:100...) y en negrita a la derecha de la barra de estado. Una página
sin escala muestra ahí <b>Sin escala</b> en rojo, y sus medidas están en tamaño de papel
(pulgadas sobre el plano). Haga clic en cualquiera de las dos para abrir Establecer escala; ambas siguen la página en la que está y
cambian en cuanto se establece, se calibra o se deshace una escala. La primera medición en una página sin
escala (una vez por página) también muestra un aviso encima de la página que lo indica, con un botón
<b>Establecer escala...</b>; desaparece cuando la página recibe una escala, o con su botón de cerrar. Conteo y Ángulo
no dependen de la escala y no muestran el aviso.</li>
<li><b>Mostrar barra de escala</b> (menú Ver, menú Medir, el pequeño icono junto a "Establecer escala" en el
grupo Escala de la página de la pestaña Medir, y
Preferencias &gt; Páginas y visualización): dibuja una escala gráfica en la esquina inferior izquierda de cada página
que tiene escala: segmentos alternos negros y blancos con números redondos en las unidades del dibujo
(0 5' 10' 15' 20' para pies y pulgadas, 0 1 2 3 4 m para metros; los milímetros pasan a
metros en tramos largos). Elige una longitud adecuada al zoom, así que mantiene un tamaño útil al
acercar y alejar, y está sobre un fondo propio para que se lea en dibujos claros y oscuros
(oscuro en el modo nocturno). Es solo en pantalla: nunca se imprime, se exporta ni se guarda en el
archivo. Su elección se recuerda.</li>
<li><b>Leer escalas de los cuadros de rótulo</b> (menú Medir, pestaña Medir): para todo un juego de una vez,
cada página recibe la escala que indica su propio cuadro de rótulo; las páginas marcadas como sin escala o sin
nota se dejan como están y se enumeran. Confíe, pero compruebe: un plano impreso a tamaño reducido (un
24x36 en papel de 11x17) sigue indicando su escala original, y nada en la página lo advierte. Mida
una dimensión conocida después de leer las escalas, y use Calibrar cinta métrica si no coincide.</li>
<li><b>Longitud</b> (Shift+M), <b>Longitud de polilínea</b>, <b>Área</b> con perímetro (Shift+A) y
<b>Conteo</b> (Shift+C, con grupos con nombre). Los valores se actualizan cuando edita la marca o cambia
la escala. Un marcador de Conteo copiado con Duplicar (Ctrl+D) o con copiar y pegar toma el siguiente
número de su grupo.</li>
<li><b>Cota</b> (Shift+D; pestaña Medir, grupo "Más", el menú Medir y el botón Medir de la pestaña CAD),
como la Cota de Bluebeam y la cota alineada de AutoCAD: haga clic en los dos puntos que va a medir, luego
mueva el puntero y haga clic donde va la línea de cota (en el modo del mouse Estándar también puede
arrastrar del primer punto al segundo y luego hacer clic). Dibuja dos líneas de extensión desde los
puntos, una línea de cota con puntas de flecha entre ellas y la longitud sobre la línea, en la escala y la
unidad de la página, igual que mide Longitud; el texto se lee derecho también en páginas giradas. Escape
cancela. Arrastre sus pinzamientos para cambiarla: los dos puntos medidos (se vuelve a medir) o el
pinzamiento en el medio de la línea de cota (más cerca o más lejos de los puntos). El color y el ancho de
línea, la <b>Punta de flecha</b> (cerrada, abierta, barra oblicua, punto o ninguno) y el tamaño del texto
están en Propiedades. Es una línea de cota PDF estándar, así que otros visores de PDF también la
muestran.</li>
<li>Más mediciones (pestaña Medir, grupo "Más", y menú Medir):
<b>Ángulo</b>: haga clic en un extremo, en el vértice y luego en el otro extremo; muestra el ángulo en grados.
<b>Radio</b>: arrastre desde el centro de un círculo hasta su borde; dibuja el círculo y muestra el
radio (R) y el diámetro (&Oslash;).
<b>Perímetro</b>: haga clic en las esquinas, haga doble clic o presione Enter; muestra la distancia alrededor.
<b>Volumen</b>: haga clic en las esquinas del área, haga doble clic o presione Enter; muestra el área
&times; la profundidad. Defina la <b>Profundidad</b> en el panel de propiedades, en la unidad de la escala de la página (pies
cuando la escala está en pies y pulgadas); cambiarla actualiza la medición seleccionada.</li>
<li><b>Resumen de mediciones</b> suma todo y exporta a CSV.</li>
</ul>

<h2 id="pages">Páginas</h2>
<ul>
<li><b>Girar página a la izquierda / Girar página a la derecha:</b> Ctrl+Shift+Minus / Ctrl+Shift+Plus.</li>
<li><b>Recortar páginas</b> (menú Páginas, pestaña Páginas, menú Herramientas): arrastre un cuadro alrededor de lo que desea conservar y luego
elija <b>Esta página</b> o <b>Todas las páginas</b> (en las demás páginas, el mismo cuadro se mide desde su
esquina superior izquierda). Solo cambia la zona visible; no se elimina nada, así que <b>Quitar recorte...</b>
(menú Páginas, pestaña Páginas) vuelve a mostrar la página entera, en esta página o en todas. Ctrl+Z deshace
cualquiera de los dos.</li>
<li><b>Tamaño de la lista de páginas:</b> arrastre el borde del panel Páginas para hacerlo tan estrecho como quiera; las
miniaturas se reducen para caber (el botón de bloqueo indica entonces solo Bloqueado / Desbloqueado). Las pestañas que no caben
se desplazan lateralmente.</li>
<li><b>Bloqueo del orden de las páginas:</b> el botón de bloqueo encima de las miniaturas (bloqueado de forma predeterminada) protege
el orden de las páginas: mientras está bloqueado, nada mueve, agrega ni quita páginas, ya sea arrastrando,
con el menú Páginas, con la cinta o con un método abreviado (Mover página hacia arriba / hacia abajo, Eliminar páginas, Insertar páginas, Insertar
página en blanco, Cortar, Pegar y Duplicar páginas). Usar uno de ellos pregunta si desea desbloquear primero.
Copiar páginas, girar y extraer funcionan mientras está bloqueado.</li>
<li><b>Reordenar:</b> desbloquee la lista de páginas y arrastre las miniaturas (varias páginas seleccionadas se mueven
juntas, y Ctrl+Z deshace todo el arrastre); o use Mover página hacia arriba / Mover página hacia abajo
(Ctrl+Shift+Up / Down; en la pestaña Páginas, en la flecha del grupo Ordenar).</li>
<li><b>Combinar archivos</b> (Archivo &gt; Combinar archivos..., o pestaña Páginas &gt; Combinar): crea un
PDF nuevo a partir de varios. Agregue los PDF (Agregar archivos…, o suéltelos en la lista desde el Explorador); el
documento abierto ya está en la lista. Arrástrelos, o use Subir / Bajar / Ordenar por nombre, para
definir el orden, de arriba abajo. Con "Agregar un marcador para cada archivo" marcado, cada archivo recibe un
marcador con su nombre y conserva sus propios marcadores debajo. Haga clic en Combinar…, elija un nombre,
y el PDF combinado se abre. Los archivos protegidos con contraseña piden su contraseña. Los archivos originales
no se modifican, y el PDF nuevo no puede reemplazar a ninguno de ellos.</li>
<li>Combinar archivos también acepta imágenes (JPG, PNG, TIFF, BMP, GIF, WebP): cada una se convierte en una página.
<b>Crear PDF desde imágenes...</b> (menú Archivo, pestaña Páginas &gt; grupo Crear) empieza con imágenes: elíjalas, póngalas
en orden y haga clic en Crear…. Con "Poner cada imagen en una página Carta" marcado (el valor
predeterminado), cada imagen se ajusta en una página Carta girada según convenga (horizontal para las imágenes
anchas); desmárquelo para que cada página tenga el tamaño propio de la imagen. Las fotos del teléfono salen derechas,
las fotos JPEG no se vuelven a comprimir (sin pérdida de calidad), y cada página de un escaneo TIFF de varias páginas
se convierte en una página.</li>
<li><b>Insertar páginas desde archivo</b> (menú Páginas, pestaña Páginas) inserta archivos PDF e imágenes (JPG, PNG,
TIFF, BMP, GIF, WebP; elija varios a la vez), en el orden elegido, después de la página actual, al
final o al principio, como un solo paso de deshacer. Cada imagen se convierte en una página del tamaño de la página
anterior, girada según convenga a la imagen. Sin nada abierto, crea con ellos un PDF nuevo, sin
guardar.</li>
<li><b>Reemplazar páginas</b> (menú Páginas; pestaña Páginas, en la flecha junto a Extraer) pone una
nueva revisión de los planos en lugar de los anteriores y conserva todo lo que se les agregó (Reemplazar páginas de
Acrobat, la sustitución de hojas de Bluebeam). Elija el PDF de la nueva revisión y luego indique las páginas por
número (las páginas 3-5 de este documento reemplazadas por las páginas 1-3 del archivo nuevo, emparejadas en orden) o
elija <b>Emparejar planos por número de plano</b>: los números de plano se leen en los cuadros de rótulo de
ambos archivos (como los lee Vincular referencias a planos) y cada página de este documento se empareja con la página del
archivo nuevo que tiene el mismo número. Revise la lista antes de hacer clic en Reemplazar: corrija un emparejamiento
escribiendo la página del archivo nuevo en "Reemplazada por la página", o déjela vacía para dejar esa página como está.
Las páginas sin pareja se dejan como están, y los planos del archivo nuevo que no corresponden a ninguna página se
enumeran debajo de la lista, para que lo sepa. Solo cambia el dibujo de la página (su contenido, sus cuadros de página
y su rotación): la página misma se queda, así que sus marcas, vínculos, campos de formulario, escala y marcadores se
quedan, y los marcadores y vínculos de otras páginas siguen llevando a ella. Cuando una página nueva tiene otro
tamaño, elija si las marcas se <b>escalan a la página nueva</b> (con su texto y sus grosores de línea; estiradas si sus proporciones difieren; una escala
pareja ajusta también la escala de medición de la página y su nombre: 1/4" = 1'-0" pasa a 1/2" = 1'-0" en
una hoja del doble de tamaño) o se <b>mantienen en el mismo lugar</b>, medido desde la
esquina superior izquierda. Las mediciones se vuelven a medir cuando cambia lo que miden (la página nueva trae
su propia escala, o las marcas se estiraron o escalaron en una página sin escala). Los subrayados y el texto de los vínculos hechos con KanzonasPDF se vuelven a dibujar en
el dibujo nuevo; un vínculo sobre palabras que no están en el mismo lugar en el dibujo nuevo (una referencia a un
plano que se movió) se queda donde estaba y se informa, para que pueda revisarlo. Los encabezados, pies de página,
marcas de agua, fondos y ediciones de texto escritos en el dibujo anterior se van con él. Las capas de los dibujos
nuevos se suman a las capas del documento (pestaña Capas), activadas o desactivadas como en el archivo nuevo. Las
marcas de las páginas del
archivo nuevo no se traen, y el archivo nuevo no se modifica. Ctrl+Z deshace todo el reemplazo en un solo paso. Un
documento protegido contra cambios lo rechaza.</li>
<li>Menú Páginas: Insertar página en blanco después de la actual (del mismo tamaño que la página actual), Extraer
páginas a un archivo nuevo (a un archivo nuevo, no al propio documento), Eliminar páginas (las páginas seleccionadas en
la lista de páginas, o la página actual; pregunta primero, y Ctrl+Z las recupera). Un marcador a una
página eliminada lleva entonces a la página siguiente (o a la última página).</li>
<li>Pestaña <b>Capas</b>: muestre u oculte las capas de CAD / de contenido opcional.</li>
<li>Pestaña <b>Marcadores</b>: agregue, cambie el nombre, reordene y aplique sangría a los marcadores.</li>
<li><b>Vincular referencias a planos</b> (menú Páginas; pestaña Páginas, en la flecha del grupo Documento): para un juego de planos trazado sin
hipervínculos. KanzonasPDF lee el número y el título de cada plano en su cuadro de rótulo (el
valor que sigue a un rótulo SHEET, SHEET NO o DWG NO, o el número con aspecto de número de plano más grande de la
zona del cuadro de rótulo) y los muestra para que los corrija. Luego, cada globo de llamada, nota o línea de índice
que nombra uno de esos planos (3/A-501, SEE A-201; A101 y A-101 cuentan como el mismo) se convierte en un
vínculo a esa página; un número que no es una página de este documento, pero que figura en el nombre de un PDF de la misma
carpeta (A-501 Details.pdf), se vincula a ese archivo. Las palabras que ya tienen un vínculo no se tocan,
así que los propios hipervínculos de AutoCAD se quedan y ejecutarlo dos veces no agrega nada. Opciones: un rectángulo azul delgado
alrededor de los vínculos (desactivado de forma predeterminada, para mantener limpios los dibujos) y marcadores con el número
y el título de cada plano. Ctrl+Z lo deshace todo.</li>
</ul>

<h2 id="scan">Escanear</h2>
<p><b>Escanear...</b> (menú Archivo, pestaña Páginas &gt; grupo Crear, o la paleta de comandos)
escanea páginas desde un escáner, o una impresora que escanea, a un PDF. Se comunica con la
mayoría de las impresoras de red sin instalar sus controladores, de cualquiera de estas formas:</p>
<ul>
<li><b>eSCL (AirScan)</b>: el escaneo sin controladores de las impresoras Mopria y Apple
AirPrint (la mayoría de las impresoras fabricadas en los últimos diez años). Se encuentran solas
en la red.</li>
<li><b>WSD</b> (Web Services on Devices): el escaneo en red de Microsoft, que ofrecen muchas
impresoras (Dell, Brother, Canon, Epson, HP, Kyocera, Xerox...). Se encuentran solas; en muchas
impresoras primero hay que activarlo en la página web de la impresora (WSD en Habilitar,
Enable).</li>
<li><b>WIA</b> (Windows): los escáneres que el propio Windows conoce, incluidos los escáneres
USB y los que tienen instalado el controlador del fabricante.</li>
<li><b>SANE</b> (Linux): los escáneres que conoce el comando scanimage (instale el paquete
sane-utils; sane-airscan le agrega los escáneres de red sin controladores).</li>
<li>En macOS, por ahora eSCL y WSD (allí aún no se admiten escáneres USB).</li>
</ul>
<p>Para escanear:</p>
<ul>
<li>La ventana muestra los escáneres que encontró, cada uno con la forma de llegar a él (eSCL,
WSD, WIA o SANE) y su dirección; una impresora encontrada de varias formas aparece una vez por
cada una. Elija uno; el último escáner usado aparece y queda elegido. <b>Actualizar</b> busca
de nuevo.</li>
<li><b>Agregar por dirección...</b>: cuando su impresora no aparece (el Wi-Fi de invitados,
algunos routers y las subredes distintas bloquean la búsqueda), escriba su dirección IP, que se
ve en su panel o en su informe de configuración de red (por ejemplo 192.168.1.20). KanzonasPDF
prueba primero eSCL y luego WSD.</li>
<li>Elija el <b>Origen</b> (Cama plana (vidrio), Alimentador de documentos o Alimentador de
documentos, ambas caras, si el escáner los tiene), el <b>Color</b> (Color, Escala de grises,
Blanco y negro), la <b>Resolución</b> (la que ofrece el escáner; 300 ppp va bien para
documentos y para el OCR) y el <b>Tamaño de página</b> (Carta, Oficio, A4 o lo más grande que
permita el escáner). Se recuerdan para la próxima vez.</li>
<li>Haga clic en <b>Escanear</b>. La ventana muestra el avance y <b>Cancelar</b> lo detiene.
Desde el alimentador de documentos se escanean todas las páginas que tenga. Luego <b>Escanear
más páginas</b> agrega más (ponga la página siguiente en el vidrio, o el siguiente montón en el
alimentador) y <b>Listo</b> las pone todas en un PDF.</li>
<li><b>Iniciar el escaneo en la impresora</b> (impresoras WSD): mientras la ventana muestra una
impresora WSD, KanzonasPDF le pide que muestre esta computadora como destino de escaneo
("KanzonasPDF - " y el nombre de la computadora). En el panel de la impresora elija Escanear,
luego Escanear a computadora (WSD), elija ese nombre y presione Iniciar: las páginas llegan a la
ventana, con la configuración de la ventana (elija allí el origen primero). Windows pregunta una
vez si permite que KanzonasPDF use redes privadas: permítalo, o la impresora no puede llegar a
la ventana. La impresora olvida esta computadora cuando se cierra la ventana.</li>
<li><b>Poner las páginas en</b>: <b>Un documento nuevo</b> (una pestaña sin guardar; Guardar
pregunta dónde guardarlo) o <b>Este documento, después de la página actual</b> (Ctrl+Z las
quita todas de nuevo en un paso). Marque <b>Hacer las páginas buscables</b> para ejecutar
Reconocer texto (OCR) en las páginas nuevas.</li>
<li><b>Vigilar una carpeta...</b> es para una impresora que solo puede escanear a una carpeta
de red (Escanear a carpeta de red, SMB) o a FTP: elija la carpeta a la que escanea; cada PDF o
imagen nuevo (JPEG, PNG, TIFF) que llega allí mientras la ventana está abierta se agrega como
páginas escaneadas. Haga clic en Listo cuando estén todos.</li>
</ul>
<p>Cuando no funciona, la ventana dice por qué con palabras sencillas, y qué probar:</p>
<ul>
<li><b>No se encontraron escáneres</b>: la computadora y la impresora deben estar en la misma
red (no en un Wi-Fi de invitados); pruebe Agregar por dirección con la dirección IP de la
impresora. Si Windows pregunta si permite que KanzonasPDF use redes privadas, permítalo: así
vuelven las respuestas de las impresoras.</li>
<li><b>El escaneo WSD está desactivado</b>: abra la página web de la impresora (escriba http://
y su dirección IP en un navegador web), busque WSD (suele estar en Red, Protocolos o
Servicios), póngalo en Habilitar (Enable), guarde y haga clic en Actualizar.</li>
<li><b>El escáner no acepta un escaneo desde la computadora</b>: algunas impresoras solo
escanean cuando el escaneo se inicia en su propio panel: deje abierta la ventana Escanear con la
impresora elegida y, en la impresora, elija Escanear a computadora (WSD) y el nombre de esta
computadora.</li>
<li><b>Una Dell E525w, o una impresora parecida</b>: active WSD en su página web (arriba) y
pruebe las dos formas: haga clic en Escanear en KanzonasPDF (iniciado desde la computadora); si
la impresora no lo acepta, inicie el escaneo en el panel de la impresora con Escanear a
computadora (WSD) y el nombre de esta computadora (iniciado desde la impresora). Si ninguna
funciona, use Copiar detalles.</li>
<li><b>Copiar detalles</b> copia lo que se encontró y las respuestas del propio escáner (nada
personal; los números de serie se omiten). Si su escáner sigue sin funcionar, péguelos en un
issue en la página de GitHub de KanzonasPDF para que se pueda admitir.</li>
<li>Seguridad: KanzonasPDF solo se comunica con el escáner que usted elige (o la dirección que
escribe), lee sus respuestas con límites estrictos de tamaño y de tiempo, y no envía nada a
ningún otro lugar. Los escáneres de red usan sus propios certificados autofirmados para HTTPS;
cada uno se acepta solo para su escáner.</li>
</ul>

<h2 id="printprod">Producción de impresión (pestaña Imprimir)</h2>
<p>Lo que necesita una hoja antes de ir a un trazador o a una imprenta. La pestaña <b>Imprimir</b> tiene estos
comandos junto a Imprimir y Recortar; también están en <b>Páginas &gt; Producción de impresión</b>.</p>
<ul>
<li><b>Establecer cuadros de página</b>: además del cuadro de recorte (lo que se muestra), una página PDF puede tener un
<b>cuadro de recorte final</b> (el tamaño terminado, donde se corta la hoja), un <b>cuadro de sangrado</b> (hasta dónde
llega el dibujo más allá del recorte final, para que no se vea un borde blanco después de cortar) y un <b>cuadro de
arte</b> (el contenido significativo). Para cada uno elija Dejar como está, Establecer o Quitar; un cuadro se establece
por sus márgenes hacia dentro desde la página tal como se muestra (los márgenes positivos van hacia dentro), en puntos,
pulgadas o milímetros, en todas las páginas, la página actual o una lista de páginas. Un cuadro tiene que quedar dentro
de toda la hoja de la página (su cuadro de medios), y el cuadro de sangrado tiene que contener el cuadro de recorte final:
si no, lo indica y no cambia nada. Ctrl+Z lo deshace.</li>
<li><b>Mostrar cuadros de página</b> (también en el menú Ver) delinea los cuadros que tiene una página: recorte final en
verde, sangrado en rojo, arte en azul, cada uno con su nombre en una esquina (Recorte final, Sangrado, Arte; solo en
pantalla).</li>
<li><b>Corregir líneas finas</b>: las líneas dibujadas más finas que un grosor que elija (0,25 pt de forma
predeterminada; incluido un grosor de 0, que significa «lo más fino que puede dibujar el dispositivo», a menudo demasiado
tenue en un trazador) se dibujan con el grosor que elija, en todas las páginas, la página actual o una lista de páginas.
Funciona en el dibujo propio de la página y en los grupos de dibujo que coloca (un grupo que también colocan otras páginas
ensancha sus líneas allí también); todo lo demás de cada línea queda igual. Las marcas conservan sus propios grosores.
Ctrl+Z lo deshace.</li>
<li><b>Revisar para imprimir</b> enumera lo que suele fallar en la imprenta, por tipo, cada cosa con su página (haga
doble clic en una línea para ir allí): fuentes no incrustadas (la imprenta pone otra), imágenes de menos de 150 píxeles
por pulgada a su tamaño impreso, imágenes en colores RGB (una prensa de cuatricromía las convierte), tamaños de hoja
mezclados, páginas sin cuadro de recorte final o sin sangrado más allá de él, y líneas más finas que 0,25 pt (con un botón
para Corregir líneas finas). Es una revisión rápida de problemas comunes, no una verificación previa según una norma de
impresión como PDF/X.</li>
<li><b>Marcas de corte</b> (en la ventana Imprimir): marcas en las esquinas del cuadro de recorte final de cada página,
por fuera de él, y el dibujo impreso hasta el cuadro de sangrado; una página sin cuadro de recorte final se marca en sus
bordes. Están solo en el papel: el archivo no cambia. El cuadro de recorte final, con espacio para las marcas, se ajusta
al papel (Ajustar al papel o Tamaño real, como se elija allí).</li>
</ul>

<h2 id="forms">Formularios</h2>
<ul>
<li><b>Rellenar:</b> con Seleccionar o Mano, haga clic en un campo. Los botones de opción con el mismo nombre de
grupo son excluyentes: elegir uno desmarca los demás de su grupo. Se respeta la longitud máxima de un campo; una lista
desplegable que lo permite también acepta un valor escrito (Escribir un valor...). KanzonasPDF no ejecuta el JavaScript
de un formulario: los totales que el formulario calcula por sí mismo y los formatos de número o fecha escritos como scripts
no se actualizan (revíselos, o rellene ese formulario en Acrobat Reader).</li>
<li><b>Campo de formulario siguiente</b> (Tab) y <b>Campo de formulario anterior</b> (Shift+Tab), en el menú Formularios:
recorren los campos en orden de lectura (página por página, de arriba abajo, de izquierda a derecha tal como se
muestra la página, también en una página girada). El
campo actual recibe un contorno naranja; un campo de texto se abre para escribir (Tab avanza, Shift+Tab
retrocede); en una casilla de verificación, un botón de opción, una lista desplegable o un campo de firma o de iniciales, presione
<b>Espacio</b> o <b>Enter</b> para rellenarlo. Esc borra el contorno.</li>
<li><b>Resaltar campos de formulario</b> (menú Ver o Formularios, activado de forma predeterminada) sombrea de azul cada campo que se puede rellenar
con un contorno azul; los campos obligatorios reciben un contorno rojo. El sombreado solo se ve en pantalla.</li>
<li><b>Crear:</b> menú Formularios: campo de texto, casilla de verificación, botón de opción, lista desplegable, campo de firma,
campo de iniciales. Un <b>campo de iniciales</b> funciona como un campo de firma: quien rellena el
formulario hace clic en él para poner allí sus iniciales guardadas. Haga doble clic en un campo para cambiar su nombre y
sus opciones.</li>
</ul>

<h2 id="sign">Proteger: firmas, contraseñas, censura</h2>
<p>Todo lo de esta sección está en el menú <b>Proteger</b>.</p>
<ul>
<li><b>Firma / iniciales manuscritas:</b> Firmar (G) o Iniciales (I); luego haga clic para colocar su firma
o sus iniciales. La primera vez se le pide que las configure (dibújelas o cargue una imagen de ellas, con un
PIN opcional); para reemplazarlas más adelante, use Archivo &gt; Preferencias &gt; Usted &gt; Configurar mi firma... / Configurar mis
iniciales.... Para elegir el tamaño, <b>arrastre un cuadro</b> en lugar de hacer clic: se colocan con el ancho que
arrastre (la altura sigue sus proporciones). El tamaño que se usa con un clic se define en Archivo &gt;
Preferencias &gt; Usted (2 pulgadas para una firma y 0.75 pulgadas para las iniciales al principio). Después, la
herramienta propia del modo del mouse (Mano, Seleccionar, o Editar objetos en el modo CAD) vuelve a estar activa, para que no
coloque una segunda por accidente. Como cualquier imagen de la página, una firma colocada se puede mover o eliminar con Editar
objetos (o con Ctrl+Z justo después de colocarla).</li>
<li><b>Fecha</b> (Ctrl+;, pestaña y menú Proteger): haga clic para escribir allí la fecha de hoy, por ejemplo
junto a una firma o en el propio campo de fecha de un documento. Poner la fecha en un campo de formulario (y firmar un
campo de firma o de iniciales) funciona en un formulario protegido que permite rellenar campos de formulario y
firmar. Es independiente de la firma, para que un formulario
que ya imprime una fecha no tenga dos. El formato (como 10/08/2026 u October 08, 2026)
se define en Archivo &gt; Preferencias &gt; Usted.</li>
<li><b>Firma o iniciales en varias páginas:</b> ponga sus iniciales (o su firma) en todas las páginas,
en todas excepto la primera o la última, o en las páginas que indique, en el mismo lugar que la última que colocó
o en una esquina.</li>
<li><b>Agregar marcador de posición de firma:</b> arrastre cuadros donde deben ir las firmas o las iniciales
(elija cuál en Propiedades). <b>Aplicar todos los marcadores de posición de firma</b> rellena luego cada uno
con su firma o sus iniciales guardadas y la fecha.</li>
<li><b>Firmar digitalmente con certificado</b>, con un bloqueo opcional contra cambios (certificar).
Elija de dónde proviene el certificado:
<ul>
<li><b>Certificado almacenado en Windows</b> (solo en Windows; no aparece en Linux ni en macOS): la lista muestra los certificados de firma de su
almacén Personal de Windows, los mismos que usan Adobe Acrobat y PDF-XChange Editor (abra
certmgr.msc &gt; Personal &gt; Certificados para verlos). Windows realiza la firma, así que
también funcionan los certificados cuya clave no se puede copiar, las tarjetas inteligentes y los tokens USB; Windows pide
el PIN cuando la clave lo necesita. Para agregar allí un .pfx/.p12, haga doble clic en él. KanzonasPDF
recuerda el certificado que usó por última vez.</li>
<li><b>Mi certificado personal</b>: uno que KanzonasPDF crea para usted la primera vez. Solo firma
documentos. No es una entidad de certificación y no puede emitir otros certificados.</li>
<li><b>Archivo de certificado</b>: un archivo .pfx/.p12 de una entidad de certificación o de su empresa,
con su contraseña.</li>
</ul> Los archivos firmados se abren como de solo lectura para que
la firma siga siendo válida (un archivo cuyos campos de firma están todos vacíos no está firmado y se abre
normalmente). <b>Detalles de la firma digital</b> muestra quién firmó y si la firma sigue
siendo válida. <b>Borrar todas las firmas digitales</b> las quita (los campos vacíos se quedan).</li>
<li><b>Agregar sello de tiempo al documento:</b> obtiene un sello de tiempo de confianza de un servidor de hora gratuito de internet,
que demuestra que el archivo existía, sin cambios, en ese momento. Se guarda como una copia nueva.</li>
<li><b>Censura:</b> la herramienta Censurar (Shift+R) o Buscar y censurar marcan zonas. Las marcas de censura
se pueden seleccionar, mover y redimensionar; <b>Aplicar las censuras seleccionadas</b> aplica solo las
seleccionadas, y Aplicar censuras las aplica todas. Aplicar quita, no solo cubre: el texto, las imágenes
y los trazos que están debajo de una marca, y cualquier <b>campo de formulario o marca</b> con el que se superponga una marca (guardan su
propia copia del texto). Un trazado vectorial que toca una marca se quita más allá del cuadro, incluida
la parte que queda fuera de él. Aplicar elimina los metadatos, los archivos adjuntos, el texto oculto y los scripts, a menos que
lo desactive en la confirmación (la casilla empieza marcada). <b>Buscar y censurar</b> también encuentra el texto donde no puede ir un cuadro: campos
de formulario (valores, opciones de lista, información sobre herramientas y nombres), vínculos (direcciones web y de correo electrónico), notas
de marcas, títulos de marcadores, propiedades del documento, el texto alternativo de los PDF etiquetados, las notas de
vínculos, las etiquetas de página y los nombres de destinos. Al aplicar, los campos, los vínculos, los sellos y los
archivos adjuntos que lo contienen se eliminan, y en las notas y los comentarios (que se quedan), los marcadores
y las propiedades (y en esos otros lugares) se reemplaza por [redacted]. Si el texto solo está en esos lugares, Buscar y censurar ofrece quitarlo de
inmediato. Una <b>leyenda</b> se vuelve a dibujar con las marcas que quedan, en el mismo paso: sus
filas ya no muestran lo censurado, y en su título el texto se reemplaza por [redacted] (un cuadro
dibujado sobre una leyenda la quita). Revise el resultado antes de compartirlo; Deshacer funciona hasta que cierra el archivo.</li>
<li><b>Sanear documento:</b> quita los datos ocultos que elija: información del documento, scripts,
archivos adjuntos, texto oculto, vínculos, comentarios, datos de formularios, miniaturas. Los scripts incluyen los de otras acciones (multimedia), los vínculos javascript: y los scripts de un formulario XFA
(los campos normales del formulario se conservan).</li>
<li><b>Propiedades de seguridad (contraseñas y permisos):</b> cifrado AES-256. Si pulsa Aceptar sin marcar ninguna
casilla en un documento protegido, se le pregunta antes de quitar su protección.
  <ul>
  <li><i>Contraseña de apertura:</i> nadie puede leer el archivo sin ella. Es una protección real; si
  la olvida, el archivo no se puede recuperar.</li>
  <li><i>Contraseña de permisos:</i> elija lo que pueden hacer los demás (imprimir, copiar, comentar, rellenar formularios,
  cambiar el contenido, cambiar las páginas). Acrobat, PDF-XChange, Bluebeam y esta aplicación la respetan, pero
  algunas herramientas gratuitas la ignoran, así que no confíe en ella para proteger secretos.</li>
  <li><i>Formularios rellenados:</i> cuando <b>Rellenar campos de formulario y firmar</b> no está permitido, los
  campos del formulario también pasan a ser de solo lectura de inmediato (Ctrl+Z lo deshace), lo cual respeta todo lector de PDF,
  incluidos los navegadores web, de modo que las respuestas no se pueden cambiar. En un formulario ya rellenado,
  o cuando protege un documento que acaba de firmar, esta casilla empieza desmarcada; márquela para entregar
  un formulario para que otras personas lo rellenen. Volver a permitir el rellenado de formularios, o Quitar seguridad, desbloquea
  los campos bloqueados de esta manera (los campos que ya eran de solo lectura antes lo siguen siendo). KanzonasPDF tampoco
  rellena los campos de solo lectura.</li>
  <li><i>Directivas:</i> guarde su configuración habitual como una directiva con nombre (las contraseñas nunca se guardan).</li>
  </ul>
  Los cambios surten efecto al guardar. Todavía no se pueden agregar firmas digitales ni sellos de tiempo a un
  PDF protegido con contraseña: quite la seguridad, firme la versión final y no agregue una
  contraseña después (eso invalidaría la firma). <b>Quitar seguridad</b> elimina la protección (necesita la
  contraseña de permisos). <b>Desbloquear con contraseña</b> le permite editar un archivo restringido y
  acepta la contraseña de permisos de un archivo que ya le permite editar, para poder cambiar su
  protección; Propiedades de seguridad y Quitar seguridad piden primero esa contraseña cuando el
  archivo tiene una. Un archivo protegido contra cambios se abre sin mensaje (el título de la
  ventana dice [protegido] y la barra de estado explica por qué); al intentar cambiarlo se explica y se indica
  Desbloquear con contraseña.</li>
<li><b>Guardar conserva la protección:</b> un archivo protegido con contraseña sigue protegido cuando guarda
sus cambios, exactamente como estaba: el mismo cifrado, la misma contraseña de apertura, la misma contraseña
de permisos y las mismas restricciones, aunque usted no conozca la contraseña de permisos. (Solo en el caso
poco común de que la protección no pueda conservarse, KanzonasPDF pide las contraseñas originales.) Use
Propiedades de seguridad (la protección nueva usa AES-256) o Quitar seguridad para cambiar la protección a
propósito.</li>
<li><b>Guardar conserva las firmas:</b> un archivo con firma digital que no ha modificado se guarda como una
copia exacta (Guardar o Guardar como), así que sus firmas siguen siendo válidas. Solo después de "Editar de todos modos" guardar
lo modifica, y entonces la firma deja de validarse.</li>
</ul>

<h2 id="document">Herramientas de documento</h2>
<ul>
<li><b>Reconocer texto (OCR):</b> hace que las páginas escaneadas se puedan buscar y seleccionar. Elija las
<b>páginas</b> (Todas, la página actual o una lista como 1-3, 7), si desea <b>omitir las páginas que
ya contienen texto</b> (activado de forma predeterminada, para que el texto no se duplique) y la <b>precisión</b>:
<b>Rápida</b> (150 ppp) para escaneos limpios con texto de tamaño normal; <b>Normal</b> (300 ppp);
<b>Alta</b> (400 ppp, y revisa todas las orientaciones, para letra pequeña, escaneos de mala calidad y
páginas de lado o al revés; la más lenta); o <b>Automática</b> (el valor predeterminado), que lee cada
página rápido y la vuelve a procesar con resolución Alta solo cuando el texto salió pequeño o poco claro.
Una precisión mayor tarda más, y nunca procesa un escaneo con más nitidez de la
que se escaneó (eso solo agrega desenfoque), así que en un escaneo de 200 ppp Normal y Alta leen a 200 ppp.
Su elección se recuerda. Una página se lee de a un mosaico por vez, cada uno dibujado solo cuando se lee,
así que incluso un plano de 42 x 30 pulgadas en Alta necesita más o menos la misma memoria que una página carta; la
memoria que usó el OCR vuelve al sistema cuando termina, y la del propio motor de OCR (unos 45 MB) dos minutos
después de la última página que leyó. Con cualquier precisión, una página escaneada al revés se detecta y se lee
girada a la posición correcta, y las líneas que están al revés o en vertical en la página reciben su texto
donde están sus letras, de modo que Buscar, así como Buscar y censurar, abarcan las palabras correctas. Editar texto cambia
luego las palabras del escaneo con una fuente que coincide (vea Editar el texto propio del PDF).</li>
<li><b>Censura:</b> la herramienta Censurar (marcar texto o área) (Shift+R) o Buscar y censurar
marcan zonas; Aplicar censuras quita de forma permanente lo que hay debajo. Un trazado vectorial que
toca una marca se quita más allá del cuadro. Al aplicarlas se eliminan los metadatos, los archivos adjuntos, el texto oculto
y los scripts, a menos que desactive esa opción. Revise el resultado antes de compartirlo.</li>
<li><b>Encabezado y pie de página, números de página, Bates</b>, <b>Marca de agua</b>,
<b>Comprimir (guardar una copia más pequeña)</b>, <b>Comparar documentos</b>, <b>Acoplar</b> (convertir las marcas en parte de la página).
La copia más pequeña conserva la protección con contraseña del documento (contraseña de apertura, permisos), o la
protección definida en Propiedades de seguridad y aún no guardada.</li>
<li><b>Guardar como PDF/A</b> (Archivo &gt; <b>Guardar como PDF/A...</b>): guarda una copia de archivo
que cumple PDF/A-2b (ISO 19005-2, nivel B), la norma para conservar un documento legible y con el
mismo aspecto durante décadas, que a menudo piden los tribunales, las oficinas de gobierno y los
archivos. En la copia: todas las fuentes están incrustadas (una fuente estándar que no lo está, como
Helvetica, Times, Courier, Symbol y ZapfDingbats, o Arial, Times New Roman y Courier New, que se
muestran con ellas, se incrusta a partir de las copias propias de KanzonasPDF, las mismas fuentes
con que las muestra, así que el texto se ve y mide exactamente igual que antes); los colores
quedan definidos por un perfil de color (una intención de salida sRGB, y un perfil CMYK para los
colores CMYK); los metadatos dicen que es PDF/A, con el título, el autor, el asunto y las palabras
clave iguales en las propiedades del documento y en los metadatos XMP; no hay JavaScript ni
acciones que abran un programa, reproduzcan contenido multimedia o se ejecuten solas (los vínculos a
páginas y direcciones web se conservan); cada comentario y marca tiene su propia apariencia y está
configurado para imprimirse, y los ocultos se quitan (PDF/A muestra todas las anotaciones, así que
uno oculto aparecería); los campos de formulario quedan dibujados (en lugar de dejarlos al visor) y
pierden sus acciones; la configuración de capas recibe un nombre; las funciones de transferencia,
los modos de fusión desconocidos, el suavizado de imágenes ampliadas, la compresión LZW (también
la de las imágenes escritas dentro del contenido de una página) y las versiones de PDF posteriores a 1.7 se reemplazan por lo que PDF/A permite, sin cambiar el aspecto
de las páginas. Los <b>archivos adjuntos</b> se conservan: si todos son a su vez archivos PDF/A,
la copia es PDF/A-2b; si no, es PDF/A-3b, la parte de la norma que permite cualquier archivo
adjunto (cada uno queda entonces registrado como archivo asociado al documento, con su tipo).
Las <b>firmas digitales</b> se quitan (los campos quedan, vacíos): la copia es un archivo nuevo, en
el que no podrían ser válidas; firme la copia si necesita una firma. Un documento <b>protegido con
contraseña</b> no se puede guardar como PDF/A (un archivo de archivo debe abrirse sin contraseña):
quite primero su seguridad (Proteger &gt; Quitar seguridad). El nombre propuesto es el del
documento con _PDFA añadido. Como después de Guardar como, la pestaña muestra luego la copia (los
cambios sin guardar están en ella; el archivo original queda como estaba), y una ventana indica lo
que se cambió y enumera lo que no se pudo corregir, cada cosa con su página.</li>
<li><b>Revisar PDF/A</b> (Archivo &gt; <b>Revisar PDF/A...</b>) enumera lo que impide que el
documento, tal como está ahora, sea PDF/A, por tipo, cada cosa con su página (haga doble clic en
una línea para ir allí) y si Guardar como PDF/A lo corrige; un botón allí lo guarda como PDF/A.
Lo que no se puede corregir: una fuente que no está incrustada y no es una de las fuentes estándar
(vuelva a crear el PDF con sus fuentes incrustadas), una fuente estándar cuyos anchos de carácter
en el archivo difieren de los de la fuente estándar, una página de más de 200 pulgadas o de menos
de 3 puntos, PostScript, partes guardadas en otros archivos, una compresión poco común, un texto de
más de 32.767 bytes (un comentario muy largo) o instrucciones de dibujo anidadas a más de 28 niveles. Revisa los
requisitos comunes de PDF/A-2b (y de PDF/A-3b para un archivo que dice serlo), no todos: para una
validación formal, use <b>veraPDF</b>, gratuito, de la PDF Association (verapdf.org).</li>
<li><b>Comparar documentos...</b> (menú Documento, pestaña Páginas): elija la revisión anterior (si está protegida con
contraseña, KanzonasPDF la pide) y luego
cómo comparar. <b>Texto, palabra por palabra</b> es para todo lo que se reacomoda (cartas,
especificaciones, permisos, informes): las palabras de ambos documentos se comparan en orden
de lectura, así que el texto que solo bajó una línea o una página no es un cambio. El resultado es una copia
de este documento con las palabras agregadas resaltadas en azul, una marca roja donde se quitaron palabras del
anterior (el comentario de la marca dice qué palabras) y un recuadro alrededor de cada
imagen que se agregó, se quitó o cambió de tamaño. Cada cambio es una marca cuyo comentario
dice qué cambió ("Antes: July 13  |  Ahora: draft"), que aparece en la Lista de marcas, y una página de resumen
al final los enumera todos; un cambio que se repite en todas las páginas (un encabezado) aparece una sola vez con sus
páginas. Un párrafo movido cuenta como quitado en un lugar y agregado en el otro; una página escaneada
sin capa de texto solo se compara como imagen (ejecute primero el OCR en ambos documentos para
comparar sus palabras). <b>Planos, superpuestos</b> es para planos y hojas: un documento nuevo
superpone los dos en cada página: rojo = solo en el anterior, azul = solo en este,
gris = sin cambios, con cada zona modificada encerrada en una nube y en la Lista de marcas. Si el
dibujo se movió en la hoja entre revisiones (se volvió a trazar con otro margen, por ejemplo), las
páginas se alinean primero, para que solo se vean los cambios reales; la parte superior de la página indica cuánto se
movió. Una revisión trazada en otro tamaño de papel (una hoja de 24x36 y su impresión en 11x17) se escala
primero al tamaño de la anterior, con cierta tolerancia para las líneas más gruesas que tiene una impresión reducida,
y la parte superior de la página lo indica. Dos impresiones del mismo dibujo no deberían mostrar entonces ningún
cambio; si un resultado tiene cambios por todas partes, los dos archivos no son el mismo dibujo a la
misma escala. El modo que conviene queda elegido automáticamente (texto cuando ambos documentos tienen una capa de texto
en la mayoría de las páginas); se puede elegir cualquiera de los dos.</li>
<li><b>Quitar marcas de agua...</b> (menú Documento): quita las marcas de agua de la página actual, de todas las
páginas o de páginas como 1-3, 7. Encuentra las marcas de agua agregadas con Documento &gt; Marca de agua y las
agregadas por aplicaciones que las identifican como marcas de agua (Adobe Acrobat, PDF-XChange y otras), así como las
anotaciones de marca de agua. Ctrl+Z lo deshace. Una "marca de agua" que es solo texto normal o una imagen
de la página no se puede distinguir del resto de la página; quítela con Borrar contenido o
Editar objetos.</li>
<li><b>Fondo...</b> (menú Documento; pestaña Páginas, en la flecha junto a Encabezado y pie): pone un <b>color sólido</b>, un <b>degradado</b>
(dos colores, de arriba abajo, de abajo arriba, de izquierda a derecha o en diagonal) o una <b>imagen</b> (Ajustar,
Rellenar, Estirar a la página o Centrar en su propio tamaño) detrás de todo lo que hay en la página, con la
opacidad que elija. Aplíquelo a la página actual, a todas las páginas o a páginas como 1-3, 7. Se guarda
en el archivo, así que todos lo ven, y no se toma como texto. Agregar un fondo a una página
que ya tiene uno lo reemplaza. <b>Quitar fondo...</b> lo quita de la página actual, de todas las páginas o de
las páginas que indique; Ctrl+Z deshace cualquiera de los dos. Un fondo no se puede ver a través de una página escaneada, porque
el escaneo es una imagen que cubre toda la página; para esas páginas use una Marca de agua.</li>
<li><b>Exportar</b> (Archivo &gt; Exportar a): Microsoft Word (.docx), Microsoft Excel (.xlsx),
Microsoft PowerPoint (.pptx), Dibujo de AutoCAD (.dxf), Imágenes (PNG), Imágenes (JPEG),
Texto sin formato (.txt). PowerPoint crea una diapositiva por página con una imagen de la página (para mostrarla
tal como se ve; el texto y los dibujos de una diapositiva no se pueden editar como texto y formas de PowerPoint).
Imágenes crea una imagen por página, con el nombre que elija más el número de
página (plano_p1.png, plano_p2.png...); si alguna ya existe, se le pregunta una vez antes de reemplazarlas.</li>
</ul>

<h2 id="preferences">Preferencias</h2>
<ul>
<li><b>Archivo &gt; Preferencias...</b> (Ctrl+K) reúne en una sola ventana las opciones que KanzonasPDF recuerda,
con las secciones enumeradas a la izquierda. Una opción que también tiene un comando de menú hace exactamente
lo mismo que ese comando, así que puede cambiarla en cualquiera de los dos lugares. <b>Aceptar</b> usa sus cambios y
cierra la ventana; <b>Aplicar</b> los usa de inmediato y deja la ventana abierta, para que pueda ver
el efecto y seguir ajustando; <b>Cancelar</b> la cierra sin los cambios hechos desde el último
Aplicar.</li>
<li><b>General:</b> tema (Igual que Windows, o Igual que el sistema en Linux y macOS; Claro, Oscuro), <b>Idioma</b> (Automático, el idioma de
Windows o del sistema; English; Español: menús, mensajes y este manual; el cambio se ve la próxima vez que se
inicia KanzonasPDF), Cinta (en lugar de barras de herramientas), Mostrar nombres de grupo
en la cinta, Mostrar barra de menús, Mostrar etiquetas de texto en las barras de herramientas, Buscar actualizaciones automáticamente y, en Linux,
Agregar KanzonasPDF al menú de aplicaciones y abrir los PDF con él (vea KanzonasPDF en Linux).
También le indica dónde se guarda su configuración (la carpeta data en el modo portátil). Una opción guardada
que no se puede usar (editada a mano, por ejemplo) se reemplaza por su valor predeterminado. Si aun así una
impidiera que KanzonasPDF se inicie, se inicia con la configuración predeterminada, lo avisa y anota la
anterior en settings-before-reset.txt, en la carpeta de datos.</li>
<li><b>Usted:</b> el Nombre del autor de las marcas (que se registra en las marcas nuevas y aparece en los sellos), y
Configurar mi firma... / Configurar mis iniciales..., con la indicación de si cada una ya está guardada, y Cambiar PIN…
para definir, cambiar o quitar el PIN que las protege (deje vacío el PIN nuevo para quitarlo), y
el Ancho de la firma y el Ancho de las iniciales que se usan cuando hace clic para colocarlas, y el Formato de fecha
que escribe la herramienta Fecha.</li>
<li><b>Estilos de marcas:</b> elija una herramienta a la izquierda para definir sus colores predeterminados, el grosor de línea, el tamaño
de fuente, el relleno, la opacidad, etc., la misma configuración que muestra el panel de propiedades cuando esa herramienta está
activa. Restablecer valores predeterminados devuelve una herramienta a como venía en KanzonasPDF.</li>
<li><b>Inicio y apertura:</b> volver a abrir los documentos que estaban abiertos al cerrar
KanzonasPDF (desactivado de forma predeterminada; también funciona cuando un instalador cierra KanzonasPDF para
actualizarlo, o Windows lo cierra al apagarse o cerrar la sesión), si se debe preguntar antes de cerrar con varios documentos abiertos (activado
de forma predeterminada), el zoom con el que se abre un
documento (Ajustar al ancho de forma predeterminada; Ajustar página, la página entera en la ventana; Tamaño real; o el zoom que tenía
cuando lo cerró) y si se debe volver a abrir en la página donde estaba la última vez.</li>
<li><b>Guardado:</b> cada cuánto hacer copia de seguridad de los cambios sin guardar (cada 5 minutos de forma predeterminada; Desactivado lo
desactiva). Se guarda una copia de cada documento con cambios sin guardar en la carpeta de copias de seguridad y se elimina cuando
lo guarda o lo cierra. Si KanzonasPDF o el equipo se detienen inesperadamente, el siguiente inicio ofrece abrir
las copias. Cuando un instalador o el apagado de Windows (en Linux, cerrar sesión o apagar) cierran KanzonasPDF, no se puede preguntar nada, así que
los últimos cambios sin guardar de cada documento se escriben primero en su copia, y el siguiente inicio los ofrece
de la misma manera. Cada una se abre en una pestaña con el nombre de su archivo original seguido de "(recuperado)", marcada como
no guardada; Guardar pregunta dónde guardarla y ofrece el archivo original (o Sin título para un PDF que
nunca se guardó). Las copias ofrecidas permanecen en la carpeta de copias de seguridad (Abrir la carpeta de copias de
seguridad) durante 30 días. <b>Carpeta de copias de seguridad</b>: Cambiar… elige otra carpeta (si KanzonasPDF no puede
escribir allí, lo indica), Usar la predeterminada vuelve a la estándar (en la carpeta data en el modo
portátil). Las copias de seguridad de los documentos abiertos se mueven a la carpeta nueva; las copias recuperadas anteriores se quedan
en la antigua. No se hacen copias de seguridad de los documentos protegidos con contraseña, porque la copia no
tendría la contraseña.</li>
<li><b>Medición:</b> las unidades que se ofrecen para una página que aún no tiene escala, a qué se redondean los pies y las pulgadas
(de 1/2" a 1/64"; 1/16" de forma predeterminada) y los decimales para las demás unidades. Las etiquetas de
medición existentes se actualizan la próxima vez que las mueve o las edita.</li>
<li><b>Mouse:</b> el modo del mouse (<b>Estándar</b>, <b>Mano</b> o <b>CAD</b>; la herramienta del modo es con la que
se inicia KanzonasPDF y a la que vuelve Escape) y las opciones de cada modo:
<ul>
<li>Estándar: Desplazar una página por paso de la rueda (activado), Movimiento libre de la página (desactivado).</li>
<li>Mano: Movimiento libre de la página (activado), Desplazar una página por paso de la rueda (activado), Hacer clic en
una marca con la Mano la selecciona (activado).</li>
<li>CAD: La rueda acerca y aleja en el cursor (Ctrl+rueda desplaza), Cursor en cruz, Lienzo abierto alrededor de las
páginas, Selección por ventana (azul) y por captura (verde), Clic, mover, clic dibuja el recuadro de selección, Mantenga
presionado el botón y arrastre para dibujar un lazo, Mostrar la pestaña CAD, Las letras escritas sobre el dibujo van a la
línea de comandos: todas activadas (la última está desactivada para quien usaba el mouse estilo CAD antes de la 1.5, así
siguen funcionando los atajos de una letra que usaba). Con el recuadro de clic, mover, clic y el lazo desactivados,
presionar, arrastrar y soltar dibuja un recuadro.</li>
</ul>
La nota debajo de Desplazar una página por paso de la rueda indica cuándo se aplica: solo mientras la página entera cabe
en la ventana, como después de Ajustar página.</li>
<li><b>Páginas y visualización:</b> bloquear el orden de las páginas, Mostrar cuadros de comentario, Resaltar campos de formulario,
Modo nocturno (líneas blancas sobre negro), Mejorar líneas finas, Mostrar barra de escala, <b>Tamaño de página del nuevo PDF</b> (el tamaño y la
orientación que usa Archivo &gt; Nuevo PDF, o Preguntar cada vez),
y <b>Cuadrícula y ajuste</b>, todo en un solo lugar: el espaciado y las unidades de la cuadrícula, el intervalo de la línea
más oscura, Mostrar cuadrícula, Ajustar a la cuadrícula y Ajustar a objetos (la misma configuración que Ver &gt; Configuración de
cuadrícula...).</li>
<li><b>OCR:</b> la precisión con la que empieza el cuadro de diálogo Reconocer texto.</li>
<li>Los cambios se aplican cuando hace clic en Aceptar; Cancelar deja todo como estaba.</li>
</ul>

<h2 id="shortcuts">Métodos abreviados de teclado</h2>
<table border="1" cellpadding="3" cellspacing="0">
<tr><th>Tecla</th><th>Acción</th></tr>
<tr><td>V / H</td><td>Seleccionar / Mano</td></tr>
<tr><td>Ctrl+E</td><td>Editar texto (clic: el párrafo; Alt+clic: una línea)</td></tr>
<tr><td>Ctrl+B / Ctrl+I / Ctrl+U (al editar texto)</td><td>Negrita / Cursiva / Subrayado de las palabras seleccionadas</td></tr>
<tr><td>Ctrl+] / Ctrl+[ (al editar texto)</td><td>Texto más grande / más pequeño (las palabras seleccionadas, de un punto en un punto)</td></tr>
<tr><td>Ctrl+P</td><td>Imprimir (con vista previa)</td></tr>
<tr><td>Ctrl+N</td><td>Nuevo PDF (página en blanco)</td></tr>
<tr><td>Shift+T</td><td>Agregar texto (escrito en la página)</td></tr>
<tr><td>Ctrl+K</td><td>Preferencias</td></tr>
<tr><td>Ctrl+;</td><td>Fecha (la fecha de hoy donde hace clic)</td></tr>
<tr><td>Shift+O</td><td>Editar objetos (las imágenes y formas propias de la página)</td></tr>
<tr><td>Ctrl+Shift+H / U / X</td><td>Resaltado / Subrayado / Tachado</td></tr>
<tr><td>C / N / T / K</td><td>Comentario / Nota / Cuadro de texto / Llamada</td></tr>
<tr><td>R / E / O / D / Y</td><td>Rectángulo / Elipse / Círculo / Nube / Polígono</td></tr>
<tr><td>L / A / Shift+L / P</td><td>Línea / Flecha / Polilínea / Lápiz</td></tr>
<tr><td>M / X</td><td>Sello / Borrador</td></tr>
<tr><td>G / I</td><td>Firma / Iniciales</td></tr>
<tr><td>Shift+M / Shift+A / Shift+C</td><td>Longitud / Área / Conteo</td></tr>
<tr><td>Shift+D</td><td>Cota</td></tr>
<tr><td>Shift+R</td><td>Censurar</td></tr>
<tr><td>Shift+E</td><td>Borrar contenido</td></tr>
<tr><td>Shift+P</td><td>Capturar área</td></tr>
<tr><td>Ctrl+rueda</td><td>Acercar o alejar alrededor del puntero (desplazarse hacia arriba y hacia abajo en el modo del mouse CAD)</td></tr>
<tr><td>Shift+rueda</td><td>Desplazarse a la izquierda y a la derecha</td></tr>
<tr><td>Shift (al dibujar)</td><td>Líneas a 45&deg;, cuadrados y círculos</td></tr>
<tr><td>Shift+clic (herramienta de dibujo)</td><td>Empezar una marca nueva encima de una existente</td></tr>
<tr><td>Ctrl+clic, Ctrl+arrastrar</td><td>Seleccionar varias marcas</td></tr>
<tr><td>Ctrl+clic en un vínculo (cualquier herramienta, cualquier modo del mouse)</td><td>Abrir el vínculo, también en una marca convertida en vínculo (un clic normal con la herramienta Mano)</td></tr>
<tr><td>Esc</td><td>Borrar la selección / soltar la herramienta (volver a la herramienta del modo del mouse: Mano, Seleccionar, o Editar objetos en el modo CAD) / cancelar un comando CAD o un recuadro de selección empezado</td></tr>
<tr><td>Supr</td><td>Eliminar lo seleccionado: las marcas, y en el modo CAD también los objetos del dibujo</td></tr>
<tr><td>Ctrl+C / Ctrl+X / Ctrl+V</td><td>Copiar / cortar / pegar (texto, marcas, imágenes, páginas)</td></tr>
<tr><td>Ctrl+A</td><td>Seleccionar todo el texto de la página (todas las páginas en la lista de páginas)</td></tr>
<tr><td>Ctrl+D</td><td>Duplicar las marcas seleccionadas (o las páginas, en la lista de páginas)</td></tr>
<tr><td>Supr (en la lista de páginas)</td><td>Eliminar las páginas seleccionadas</td></tr>
<tr><td>Ctrl+L</td><td>Bloquear las marcas seleccionadas</td></tr>
<tr><td>Ctrl+Shift+] / Ctrl+] / Ctrl+[ / Ctrl+Shift+[</td><td>Al frente / adelante / atrás / al fondo</td></tr>
<tr><td>Izquierda / Derecha, Re Pág / Av Pág</td><td>Página anterior / siguiente</td></tr>
<tr><td>Inicio / Fin</td><td>Primera / última página</td></tr>
<tr><td>Ctrl+G</td><td>Ir a la página (el cuadro de página)</td></tr>
<tr><td>Tab / Shift+Tab</td><td>Campo de formulario siguiente / anterior (Espacio o Enter lo rellena)</td></tr>
<tr><td>Teclas de flecha (con algo seleccionado)</td><td>Moverlo 1 pt; con Shift, 10 pt; con Ctrl, 0.1 pt</td></tr>
<tr><td>Ctrl+Shift+Plus / Minus</td><td>Girar la página</td></tr>
<tr><td>Ctrl+Shift+Up / Down</td><td>Mover la página</td></tr>
<tr><td>Ctrl+2 / Ctrl+0 / Ctrl+1</td><td>Ajustar al ancho / ajustar página / tamaño real</td></tr>
<tr><td>Ctrl+F, Enter / F3, Shift+Enter / Shift+F3</td><td>Buscar, coincidencia siguiente, coincidencia anterior</td></tr>
<tr><td>Ctrl+H</td><td>Reemplazar texto</td></tr>
<tr><td>Ctrl+Shift+N</td><td>Mover pestaña a una nueva ventana</td></tr>
<tr><td>Alt+Down / Alt+Up</td><td>Comentario siguiente / anterior</td></tr>
<tr><td>F1</td><td>Este manual</td></tr>
<tr><td>Ctrl+Shift+P</td><td>Paleta de comandos</td></tr>
<tr><td>Ctrl+F1</td><td>Contraer / expandir la cinta</td></tr>
<tr><td>Ctrl+Shift+M</td><td>Mostrar / ocultar la barra de menús (diseño con cinta)</td></tr>
<tr><td>F11</td><td>Activar / desactivar el modo del mouse CAD (al desactivarlo vuelve a Estándar o Mano, el que tenía)</td></tr>
<tr><td>Letras, Enter (modo CAD)</td><td>Escribir un comando en la línea de comandos (M Mover, CO Copiar, RO Girar...); Enter lo ejecuta y, con la línea vacía, repite el último. Los atajos de una sola letra de las herramientas no se aplican en el modo CAD (los de Shift y una letra, sí), salvo que Preferencias &gt; Mouse desactive escribir en la línea de comandos.</td></tr>
<tr><td>F12</td><td>Activar / desactivar el modo nocturno (líneas blancas sobre negro)</td></tr>
<tr><td>Mantener presionada la rueda + arrastrar</td><td>Desplazar (con cualquier herramienta)</td></tr>
<tr><td>Alt (al dibujar o arrastrar)</td><td>No ajustar</td></tr>
<tr><td>F4 / F6 / F7 / F8 / F9 / F10</td><td>Páginas / Propiedades / Marcas / Caja de herramientas / Marcadores / Vista dividida</td></tr>
</table>
<p>Cambie cualquier método abreviado en Ver &gt; Métodos abreviados de teclado. Una tecla solo puede usarla un comando: si dos comandos comparten una, no se cambia nada hasta que lo corrija. Una tecla que usted asignó a un comando sigue siendo suya: un atajo nuevo que una versión posterior da a otro comando no se la quita (ese comando queda sin atajo; Restablecer todos los valores predeterminados se lo devuelve). <b>Restablecer todos los valores predeterminados</b> vuelve a poner los métodos abreviados originales de inmediato. Los cambios se aplican en todas las ventanas.</p>
"""
