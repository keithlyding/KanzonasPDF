"""KanzonasPDF's user manual in Italian (Help > User manual when the interface is in
Italian): the translation of manual.MANUAL, with the same chapters (the same <h2 id>s),
tables, lists and links, and the menu commands named as the Italian interface names them
(manual.missing_from_manual checks it). A change to the English manual is made here too.
"""

MANUAL = """
<h1>Manuale utente di KanzonasPDF</h1>
<p>Un lettore ed editor di PDF gratuito. Usa l'indice a sinistra oppure scrivi nella casella
<b>Trova nel manuale</b> qui sopra.</p>

<h2 id="audit-fixes">Protezione del documento e modifica sicura</h2>
<p>Applica oscuramenti rimuove qualsiasi tracciato vettoriale che tocca un segno, anche la parte del
tracciato che si trova fuori dal riquadro. L'applicazione elimina anche metadati, allegati, testo nascosto e script,
a meno che tu non disattivi questa opzione. Controlla il risultato prima di condividerlo. Cerca e oscura
sostituisce il testo con [redacted] in note e commenti (vengono riscritti da capo, quindi nessuna copia del
testo resta nel loro aspetto o nei loro dati privati) e rimuove completamente i timbri, le immagini e
i file allegati che lo contengono, compresi i dati privati e l'aspetto dei timbri.</p>
<p>Quando salvi le modifiche a un PDF già protetto, la sua protezione resta esattamente com'era: la
stessa password di apertura, la stessa password delle autorizzazioni e le stesse autorizzazioni, senza bisogno di alcuna password. Così un modulo
bloccato con una password delle autorizzazioni che non conosci si può comunque compilare e salvare, e resta
bloccato. (Solo nel raro caso in cui la protezione non si possa mantenere, KanzonasPDF chiede
le password originali; se la richiesta non va a buon fine o viene annullata, il file esistente resta intatto.)
Cerca e oscura esamina solo il testo delle annotazioni visibili (commenti, etichette dei timbri,
nomi e date), non i loro colori o le loro forme, quindi oscurare una parola come "fill" non
elimina annotazioni che non c'entrano. I documenti appena protetti vengono esclusi dai backup automatici,
e una copia di recupero esistente viene rimossa quando si aggiunge la protezione. Ogni copia di recupero ha
una propria identità univoca, anche per file con lo stesso nome.</p>
<p><b>Stampa</b> (menu File, barra degli strumenti, Ctrl+P) apre la finestra di stampa di KanzonasPDF con un'anteprima
di ogni foglio così come verrà stampato: scegli la stampante e le copie, quali pagine (Tutte, Pagina corrente
o un elenco come 1-3, 5), l'orientamento (Automatico ruota ogni foglio per adattarlo alla sua pagina), le dimensioni
(Adatta alla carta, oppure Dimensioni reali, che riduce solo le pagine troppo grandi), se stampare le annotazioni
e i campi modulo, <b>Linee sottili scure</b> (attivo a meno che tu non lo disattivi: ogni linea viene stampata larga almeno
0,15 pt e continua, così le linee sottilissime dei disegni non risultano sbiadite o interrotte; se è disattivato,
le linee vengono stampate esattamente sottili come sono), <b>Segni di taglio</b> (vedi Produzione di stampa) e
<b>Annotazioni fuori dalle pagine</b> (proposto solo quando una pagina ha annotazioni accanto, nel grigio):
<b>Escludile</b> (viene stampata solo la pagina, come in qualsiasi programma PDF), <b>Sullo stesso foglio</b> (il foglio
comprende la pagina e ciò che le sta accanto, quindi la pagina viene stampata più piccola) oppure <b>Su un foglio
aggiuntivo dopo la pagina</b> (la pagina viene stampata alla sua dimensione, così un disegno resta in scala, e il foglio
successivo la mostra sbiadita con ciò che le sta accanto al suo posto). <b>Imposta pagina...</b> imposta il formato della carta e i margini. Usa le frecce
sotto l'anteprima per vedere ogni foglio. Le pagine vengono stampate alla risoluzione della stampante fino a 600 dpi,
elaborate una striscia alla volta, così anche i disegni grandi escono nitidi senza usare molta memoria.
Annotazioni e campi modulo seguono la propria impostazione di stampa, come in Acrobat: quelli fatti per comparire
solo sullo schermo non vengono stampati, mentre quelli fatti per essere stampati ma non mostrati sullo schermo sì. Durante la stampa, una
piccola finestra indica a quale pagina è arrivata; <b>Annulla</b> in quella finestra interrompe il lavoro.</p>
<p>Copiare, estrarre ed esportare richiedono l'autorizzazione alla copia, e lo stesso vale per Combina file e
Inserisci pagine da file per ogni PDF da cui prendono le pagine: un PDF che non consente la copia viene
rifiutato, a meno che tu non digiti la sua password delle autorizzazioni (del proprietario) quando ti viene chiesta. Stampa richiede l'autorizzazione
alla stampa e usa al massimo 150 dpi quando la stampa ad alta qualità è vietata. La compilazione dei moduli
e l'aggiunta di annotazioni rispettano autorizzazioni separate: firmare un campo modulo o inserirvi la data richiede solo
<b>Compilazione dei campi modulo e firma</b>, mentre mettere una firma o la data in qualsiasi altro punto
della pagina modifica la pagina. Un modulo con soli campi firma vuoti non è firmato, quindi si apre
per la compilazione anche se è protetto. Appiattire le pagine selezionate mantiene
le etichette di pagina, i collegamenti in uscita (e ciò che lega un collegamento alla sua sottolineatura e alle sue parole) e la
calibrazione del disegno. Appiattisci lascia come segni i segni di oscuramento non ancora applicati. L'esportazione in Excel scrive il testo del PDF come testo
letterale nelle celle, compreso il testo che inizia con un segno di uguale. L'OCR disattiva la telemetria di ONNX Runtime
prima di creare le sessioni di riconoscimento.</p>
<h2 id="start">Primi passi</h2>
<ul>
<li><b>Aprire un PDF:</b> File &gt; Apri (Ctrl+O), trascina un file sulla finestra oppure scegline uno in
File &gt; Apri recenti. Ogni file si apre in una propria scheda, alla pagina e con lo zoom in cui l'avevi lasciato (la
scheda in primo piano ha una linea blu in alto; i nomi delle altre sono un po' più tenui). Se
KanzonasPDF è già aperto, un PDF aperto da Esplora file, da un'e-mail o da un browser si apre in una nuova scheda
al suo interno e la finestra passa in primo piano (ripristinata se era ridotta a icona). Se apri un file
già aperto passi alla sua scheda; se il file è cambiato sul disco da quando è stato aperto, la scheda
lo mostra com'è adesso (chiedendo prima se la scheda ha modifiche non salvate).</li>
<li><b>Creare un nuovo PDF:</b> File &gt; <b>Nuovo PDF...</b> (Ctrl+N, oppure scheda Pagine &gt; Nuovo PDF)
chiede il formato della pagina (Lettera, Legale, Tabloid, da ANSI C a E, da ARCH A a E, da A4 ad A0) e
l'orientamento verticale o orizzontale, poi apre una scheda chiamata Senza titolo 1 con una pagina vuota. Aggiungi pagine con
Inserisci pagina vuota dopo la corrente o Inserisci pagine da file (PDF e immagini), disegna, scrivi o
firma come su qualsiasi PDF. Non viene salvato da nessuna parte finché non lo salvi: Salva (Ctrl+S) chiede dove,
come Salva con nome, e se lo chiudi dopo averlo modificato ti chiede se salvarlo. Spunta <b>Non chiedere
più</b> per usare sempre il formato che hai scelto; per cambiarlo, o per tornare a ricevere la domanda, vai in
Preferenze &gt; Pagine e visualizzazione &gt; Formato pagina del nuovo PDF. Senza documenti aperti, Inserisci pagina
vuota crea un nuovo PDF allo stesso modo, e Inserisci pagine da file crea un nuovo PDF non salvato a partire
dai file che scegli. Quando tra i file ci sono immagini, Inserisci pagine da file offre <b>Rendi le immagini
ricercabili (riconoscimento del testo, OCR)</b>, come Crea PDF da immagini (la stessa scelta,
ricordata): sulle pagine create dalle immagini il testo viene riconosciuto una volta inserite.</li>
<li><b>Salva:</b> Ctrl+S. <b>Salva con nome:</b> Ctrl+Shift+S. (Per una copia d'archivio, vedi Salva come PDF/A
in Strumenti per i documenti.) Se salvi con il nome di un file aperto in un'altra
scheda, quel file viene sostituito e quella scheda si chiude (chiedendo prima se ha modifiche non salvate); lo stesso vale
per Estrai pagine, Combina file e le copie salvate da Comprimi, Marca temporale e firma digitale,
tranne che in questo caso l'altra scheda mostra il nuovo file. Annulla è Ctrl+Z, Ripeti è Ctrl+Y. Ciò che
era selezionato resta selezionato dopo Annulla o Ripeti (a meno che il passo non lo tolga).
Vengono conservati fino a 30 passaggi. Ogni passaggio conserva solo ciò che la modifica ha cambiato, quindi annullare e ripetere è rapido
e tutti i 30 passaggi entrano anche in PDF molto grandi; la cronologia resta comunque entro un limite di memoria
(256 MB per documento, 512 MB per tutti i documenti aperti insieme; i passaggi più vecchi vengono eliminati per primi).</li>
<li><b>Pannelli:</b> Pagine/Segnalibri/Livelli a sinistra (F4), Proprietà a destra (F6),
Elenco annotazioni (F7), Cassetta degli attrezzi (F8), Segnalibri (F9), Vista divisa (F10). I pannelli che avevi aperti
quando hai chiuso KanzonasPDF (con le loro dimensioni, i loro lati e quale tra Proprietà / Cassetta degli attrezzi era in
primo piano) ricompaiono al successivo avvio; la Vista divisa all'avvio è sempre chiusa.</li>
<li><b>Un documento in una finestra a sé</b> (per un secondo monitor): trascina la sua scheda verso l'alto o verso il basso fuori
dalla barra delle schede e rilasciala, oppure fai clic destro sulla scheda &gt; <b>Sposta in una nuova finestra</b>, oppure Visualizza &gt;
<b>Sposta scheda in una nuova finestra</b> (Ctrl+Shift+N). Il documento non viene riaperto: le modifiche non salvate
e la cronologia degli annullamenti lo seguono. Rilascia una scheda sulle schede di un'altra finestra di KanzonasPDF (oppure fai clic destro
su di essa &gt; <b>Sposta nella finestra</b>) per spostarla lì. Ogni finestra ha i propri pannelli, strumenti e
casella Trova, con le stesse impostazioni. Chiudere l'ultima scheda di una finestra separata chiude quella
finestra; chiudere la finestra principale (la prima) le chiude tutte, e la riapertura degli ultimi
file all'avvio riporta i documenti di tutte le finestre nella finestra principale. Chiudere una
finestra separata con più documenti chiede conferma solo per i documenti di quella finestra. Le opzioni di visualizzazione
(griglia, aggancio, caselle dei commenti, evidenziazione dei campi modulo, visualizzazione delle annotazioni, controllo ortografico, tema, modalità del
mouse) sono le stesse in tutte le finestre: se ne cambi una, il menu di ogni finestra si adegua.</li>
<li><b>Chiudere KanzonasPDF:</b> con un solo documento aperto, ti viene chiesto di salvarlo se ha
modifiche non salvate. Con più documenti aperti ricevi una sola domanda: elenca quelli con
modifiche non salvate e propone <b>Salva tutto</b>, <b>Non salvare</b> o <b>Annulla</b> (Annulla lascia
tutto aperto); se nessuno ha modifiche non salvate chiede "Chiuderli tutti e uscire?" (puoi disattivare questa domanda
in Preferenze &gt; Avvio e apertura &gt; <b>Chiedi prima di chiudere KanzonasPDF con più documenti
aperti</b>). Chiudere una scheda chiede conferma solo per quel documento.</li>
<li><b>Barra multifunzione:</b> i comandi sono raggruppati in schede: Home, Annotazioni, Misure, Disponi, Revisione,
Proteggi, Moduli, Pagine, Stampa e Visualizza. La scheda <b>Annotazioni</b> contiene solo annotazioni: commenti, note, caselle
di testo, richiami, timbri, legende, forme e icone di file allegati. Le annotazioni restano modificabili in qualsiasi visualizzatore
PDF (Adobe Reader, browser) finché non le appiattisci. Tutto il resto che aggiungi (immagini,
Aggiungi testo, firme, sigle, date) viene scritto nella pagina stessa, quindi in un visualizzatore
appare e si comporta come appiattito; Modifica testo e Modifica oggetti (scheda Home) possono comunque modificarlo qui, come
fanno Acrobat e PDF-XChange. Apri, salva, stampa, annulla e ripeti si trovano a sinistra delle schede, e la
casella Trova (con il numero di corrispondenze e le frecce su / giù) si trova alla loro destra. La barra inferiore (barra di stato, in basso a destra) contiene la navigazione tra le pagine (prima,
precedente, numero di pagina, successiva, ultima pagina), Adatta alla pagina, Adatta alla larghezza, Dimensioni reali, un cursore dello zoom e la
casella dello zoom con riduci / ingrandisci, come in PDF-XChange Editor, le dimensioni della pagina e la
posizione del puntatore ("8.50 &times; 11.00 in&nbsp;&nbsp;(1.25, 3.40)": dall'angolo in alto a sinistra
della pagina come viene mostrata, nelle unità dei righelli), <b>Riusa</b> e la scala di disegno della pagina
corrente (in rosso se non ne ha una; fai clic per impostarla). Con <b>Riusa</b> attivo (il predefinito), dopo
aver disegnato un'annotazione il suo strumento resta scelto per la successiva; disattivo: si torna allo
strumento della modalità mouse (Seleziona, Mano o Modifica oggetti), come fa il pulsante Reuse di Bluebeam.
In entrambi i casi ciò che hai disegnato resta selezionato, così Proprietà lo modifica. Un messaggio della barra inferiore troppo lungo per
lo spazio a sinistra dei controlli di pagina termina con "..."; passaci sopra con il mouse per leggerlo per intero. La barra multifunzione è compatta: due righe di
pulsanti, e ogni scheda entra in uno schermo largo 1366 pixel, in inglese, spagnolo e italiano. I comandi usati
meno spesso condividono un pulsante con una freccia accanto: fai clic sul pulsante per il comando che mostra,
o sulla freccia per gli altri (il pulsante mostra poi l'ultimo usato). Nella scheda Home,
la freccia di Evidenzia contiene Sottolinea e Barrato, e quella di Firma contiene Sigla; nella scheda Pagine, quella di Intestazione
e piè di pagina contiene Filigrana e Sfondo, e quella di Estrai contiene Sostituisci. Altri comandi sono elencati sotto
la freccia stretta all'estremità destra di un gruppo: Impostazioni griglia accanto agli interruttori di aggancio, Sposta su
e Sposta giù nel gruppo Organizza della scheda Pagine, Allegati e Richiami tavole nel suo
gruppo Documento, Comprimi e Nomi gruppi nel gruppo Barra multifunzione della scheda Visualizza, Allinea nel gruppo
Modifica della scheda CAD. Nella scheda Home, Riduci e Ingrandisci sono icone sotto Dimensioni reali. Se la finestra
è troppo stretta per una scheda, scorrila lateralmente con la rotellina del mouse o con la barra sottile sotto di essa. Visualizza &gt; <b>Mostra i nomi dei gruppi sulla barra multifunzione</b> aggiunge un nome sotto ogni gruppo di
pulsanti (la barra diventa un po' più alta, come in Microsoft Office). Visualizza &gt; <b>Mostra barra dei menu</b> (Ctrl+Shift+M)
nasconde o mostra la barra dei menu File, Modifica, Visualizza...; quando è nascosta, il pulsante &#9776; a destra
delle schede della barra multifunzione contiene tutti i menu, e tutte le scorciatoie da tastiera continuano a funzionare. <b>Comprimi barra multifunzione</b>
(Ctrl+F1, o doppio clic su una scheda) mostra solo i nomi delle schede; fai clic su una scheda per riaprirla. Togli la spunta da
Visualizza &gt; <b>Barra multifunzione (al posto delle barre degli strumenti)</b> per le classiche barre degli strumenti compatte (zoom, numero di pagina
e Trova tornano allora nella barra degli strumenti superiore). I menu contengono sempre tutti i comandi.</li>
<li><b>Barra dei pannelli:</b> le icone sul bordo sinistro aprono i pannelli Pagine, Segnalibri, Livelli, Oggetti
e Raccolte; fai di nuovo clic sull'icona illuminata per richiudere il pannello e avere più spazio per la pagina.
Ci sono anche le icone di Elenco annotazioni e Allegati. Visualizza &gt; <b>Mostra barra dei pannelli (bordo
sinistro)</b> nasconde la barra; i pannelli mostrano allora i loro nomi come schede in basso.</li>
<li><b>Tavolozza dei comandi</b> (Ctrl+Shift+P; menu Guida, scheda Visualizza): digita alcune lettere di ciò che
vuoi fare e scegli il comando dall'elenco; Invio lo esegue. Ogni comando di menu e ogni strumento è
presente con il suo menu e la sua scorciatoia, quindi non devi cercare nulla nella barra multifunzione. Le lettere
devono solo comparire nell'ordine giusto ("sal nom" trova Salva con nome, "ruo sin" trova Ruota pagina a sinistra), e i
comandi eseguiti di recente dalla tavolozza compaiono per primi.</li>
<li><b>Modalità notturna (linee bianche su nero)</b> (F12; menu Visualizza, scheda Visualizza, Preferenze &gt; Pagine
e visualizzazione): disegna le pagine come uno schermo CAD. La luminosità viene invertita e i colori vengono mantenuti, quindi
linee e testo neri diventano bianchi su un foglio nero, mentre una linea rossa resta rossa e un'evidenziazione
gialla resta gialla. Anche immagini e scansioni vengono invertite, come un negativo. Cambia solo lo schermo:
stampa, esportazione, Cattura area e file salvato restano quelli di sempre. La tua scelta
viene ricordata.</li>
<li><b>Migliora linee sottili</b> (menu Visualizza, Preferenze &gt; Pagine e visualizzazione; attivo per impostazione predefinita):
ogni linea viene disegnata larga almeno un pixel dello schermo, come l'opzione omonima di Acrobat. I disegni
CAD usano linee molto sottili (un decimo di punto o meno); alla loro larghezza reale coprono solo
una parte di un pixel dello schermo quando lo zoom è ridotto e appaiono grigio chiaro. Con questa opzione attiva restano scure e
leggibili a qualsiasi zoom. Cambia solo lo schermo: stampa, esportazione, OCR, Confronta e file
salvato usano le larghezze reali delle linee. La tua scelta viene ricordata.</li>
<li><b>Annotazioni fuori dalla pagina:</b> metti annotazioni, immagini e disegni catturati ovunque nel grigio
attorno a una pagina: accanto a un disegno, oppure altre tavole incollate a fianco per ricomporre un disegno diviso su
più fogli (Cattura area, Shift+P, le mantiene nitide). Il grigio funziona come sempre; una pagina con annotazioni accanto
riceve solo lo spazio che serve, su quei lati (lo stesso a sinistra e a destra, così le pagine restano allineate; con
due pagine affiancate, la pagina successiva si sposta perché nulla venga coperto). Un clic o un trascinamento nel
grigio va alla pagina più vicina. Queste annotazioni vengono salvate nel file, ma <b>non vengono stampate</b> a meno
che tu non lo scelga nella finestra Stampa (Annotazioni fuori dalle pagine), e gli altri programmi PDF come Acrobat
non le mostrano (in Acrobat, al massimo si vedono riducendo lo zoom), quindi usale per le tue note. Per dare lo spazio
a tutti, usa <b>Pagine &gt; Aggiungi spazio attorno alla pagina</b>: quello spazio fa parte della pagina. <b>Adatta
pagina e annotazioni</b> (menu Visualizza e l'elenco della casella dello zoom) mostra una pagina con tutto ciò che le
sta accanto; Adatta pagina e Adatta larghezza adattano le pagine come sempre. Revisione &gt; <b>Mostra
annotazioni</b> le nasconde o le mostra tutte; <b>Mostra annotazioni sulla pagina</b> e <b>Mostra annotazioni fuori
dalle pagine</b> nascondono un tipo o l'altro (con quelle fuori nascoste, lo spazio attorno alle pagine si richiude).
Sanifica documento e Rimuovi le informazioni nascoste (quando applichi gli oscuramenti) rimuovono le annotazioni del
tutto fuori da una pagina. La prima volta in un documento che qualcosa che disegni, incolli o sposti esce dalla
pagina, KanzonasPDF chiede come stampare queste annotazioni: <b>Non stamparle</b>, <b>Stesso foglio</b> o
<b>Foglio aggiuntivo</b>; la tua risposta è l'impostazione iniziale della finestra Stampa (lì puoi cambiarla).
Seleziona <b>Non chiedere più</b> perché non lo chieda più.</li>
<li><b>Tema:</b> Visualizza &gt; Tema (Come Windows, oppure Come il sistema su Linux e macOS; Chiaro, Scuro). Visualizza &gt; Mostra etichette di testo sulle
barre degli strumenti aggiunge i nomi sotto le icone. Passa con il mouse su qualsiasi pulsante o casella della barra degli strumenti o della barra multifunzione per una
descrizione comando che indica cosa fa e la sua scorciatoia da tastiera (quella impostata in Scorciatoie da tastiera);
un pulsante che raccoglie più strumenti (Forme, Misure) indica lo strumento che mostra e il suo tasto. Nella
scheda CAD la descrizione indica le lettere da digitare nella riga di comando (Sposta: digita M e premi Invio).</li>
</ul>

<h2 id="free">Gratuito</h2>
<p>Le versioni ufficiali di KanzonasPDF restano gratuite per uso personale e commerciale: niente abbonamenti, scadenze di prova, livelli di funzioni a pagamento, account obbligatori o servizi cloud a pagamento obbligatori. Le donazioni facoltative non sbloccano mai funzioni. Il codice sorgente è disponibile con licenza GNU AGPL-3.0.</p>

<h2 id="install">Installare, aggiornare e disinstallare</h2>
<ul>
<li>Esegui <b>KanzonasPDF-v&lt;versione&gt;-setup.exe</b> (il programma di installazione ha un'icona blu; il programma vero e proprio è rosso). Non servono diritti di amministratore: viene
installato per il tuo account Windows (scegli "tutti gli utenti" nella prima pagina se sei un amministratore e
lo preferisci). Aggiunge un collegamento nel menu Start, facoltativamente un collegamento sul desktop, e propone
KanzonasPDF come app per aprire i PDF.</li>
<li><b>Impostarlo come app PDF predefinita:</b> Windows non consente ai programmi di installazione di farlo in automatico. Fai clic destro su
un PDF qualsiasi &gt; Apri con &gt; Scegli un'altra app &gt; KanzonasPDF, e spunta "Usa sempre questa app".</li>
<li><b>Miniature e riquadro di anteprima in Esplora file:</b> quando KanzonasPDF è la tua app
predefinita per i PDF, le cartelle di Esplora file mostrano la prima pagina di ogni PDF al posto
dell'icona di KanzonasPDF (nella visualizzazione Icone medie o più grandi), e il riquadro di
anteprima (Alt+P in Esplora file) ne mostra le pagine: scorrile con la rotellina del mouse, la
barra di scorrimento o i tasti freccia e Pag su/Pag giù. Sono disegnate con lo stesso motore PDF
di KanzonasPDF, e Windows le esegue fuori da Esplora file stesso. Un PDF con password mostra
l'icona, e un avviso nel riquadro di anteprima. Se una cartella mostra ancora le icone, Windows
sta mostrando le immagini che aveva conservato: vengono ridisegnate quando i file cambiano, o
subito dopo aver eliminato le "Anteprime" con Pulizia disco. Le versioni portatili non le
aggiungono (non cambiano nulla in Windows).</li>
<li>Se apri un altro PDF mentre KanzonasPDF è in esecuzione, si apre in una nuova scheda della stessa finestra.</li>
<li><b>Aggiornare:</b> usa <b>Aggiorna ora</b> nell'avviso di aggiornamento o in Guida &gt; Verifica
aggiornamenti. KanzonasPDF scarica il nuovo programma di installazione solo da GitHub e lo esegue solo se lo
sha256 del file corrisponde all'impronta pubblicata con quella versione; chiede di salvare i documenti aperti, si chiude,
installa la nuova versione sopra quella attuale (per te, o per tutti gli utenti con la richiesta di amministratore di Windows
se era stato installato così) e si riavvia. In alternativa esegui tu il nuovo programma di installazione sopra quello vecchio;
non serve disinstallare prima. In entrambi i casi viene installato nello stesso posto e mantiene
impostazioni, firme, timbri e cassetta degli attrezzi. <b>Disinstallare:</b> Impostazioni di Windows &gt; App, oppure il programma di disinstallazione nella cartella di installazione.</li>
<li><b>Versione portatile</b> (<b>KanzonasPDF-portable.zip</b>): nessuna installazione. Estrai la cartella KanzonasPDF
dove vuoi (una chiavetta USB, un'unità di rete, i tuoi Documenti) ed esegui KanzonasPDF.exe. Grazie al
file portable.txt al suo interno, impostazioni, firme, immagini dei timbri e certificato vengono conservati in una
cartella <b>data</b> accanto al programma anziché nel registro e nelle cartelle utente del computer, quindi
viaggiano con la cartella. Il titolo della finestra e Guida &gt; Informazioni riportano <b>(portatile)</b> quando
questa copia è in esecuzione in modalità portatile. Tieni insieme l'intera cartella. Il download ha lo stesso nome per ogni versione
(KanzonasPDF-portable.zip, con dentro una cartella KanzonasPDF), quindi il percorso del programma non deve mai
cambiare. <b>Per aggiornare</b>, usa <b>Aggiorna ora</b> nell'avviso di aggiornamento o in Guida &gt; Verifica
aggiornamenti: KanzonasPDF scarica il nuovo zip portatile solo da GitHub e lo installa solo
se lo sha256 del file corrisponde all'impronta pubblicata con quella versione. Chiede di salvare i documenti
aperti, si chiude, sostituisce i propri file di programma nella stessa cartella e si riavvia. Oppure fallo a mano: chiudi
KanzonasPDF ed estrai il nuovo download nella stessa cartella, sovrascrivendo i file. La cartella data viene mantenuta e, se hai impostato KanzonasPDF.exe come app PDF
predefinita (Impostazioni di Windows &gt; App &gt; App predefinite), resta quella predefinita. Suggerimento: se Estrai tutto di
Windows propone il nome di una nuova cartella, cambialo con quello della cartella che usi già.
(L'apertura di un file allegato usa comunque la cartella temporanea di Windows.)</li>
<li><b>Versione PortableApps.com</b> (KanzonasPDF Portable, per la piattaforma PortableApps.com):
impostazioni e file vengono conservati nella cartella <b>Data</b> del pacchetto, ed è la piattaforma PortableApps.com
ad aggiornarlo, quindi KanzonasPDF non verifica gli aggiornamenti né propone Aggiorna ora, a meno che tu non
riattivi Guida &gt; Verifica aggiornamenti automaticamente. Entrambe le versioni portatili seguono la chiavetta
USB su una nuova lettera di unità: se Apri recenti elenca E:\\Docs\\plan.pdf e ora la chiavetta è F:,
apre F:\\Docs\\plan.pdf.</li>
<li><b>Guida &gt; Verifica aggiornamenti:</b> chiede a GitHub se è stata pubblicata una versione più recente di KanzonasPDF.
Una finestra ti mostra la risposta. Se c'è una versione più recente, elenca <b>le novità rispetto alla tua
versione</b>: le note brevi di ogni versione più recente della tua, dalla più nuova (in italiano o in spagnolo quando
KanzonasPDF è in quella lingua e le note ci sono; altrimenti in inglese); <b>Scarica</b> apre la pagina della versione nel browser e
<b>Aggiorna ora</b> aggiorna questa copia sul posto (vedi sopra; non nella versione PortableApps.com,
che viene aggiornata dalla sua piattaforma). La verifica automatica invece mostra un avviso in fondo alla
finestra con <b>Novità</b> (le stesse note), <b>Aggiorna ora</b>, <b>Scarica</b>, <b>Salta
questa versione</b> e <b>Più tardi</b>. Non viene scaricato né installato nulla finché non fai clic su un pulsante.
Con Guida &gt; <b>Verifica aggiornamenti automaticamente</b> spuntato (impostazione predefinita) l'app verifica
in silenzio una volta al giorno: pochi secondi dopo l'avvio, e di nuovo ogni giorno finché resta aperta.
Quando non c'è nulla di più recente, la barra di stato lo segnala per qualche secondo ("Verifica aggiornamenti:
Hai già la versione più recente"). Togli la spunta per non contattare mai GitHub. Se la tua rete blocca
GitHub, la verifica automatica semplicemente non trova nulla.</li>
<li><b>Guida &gt; Segnala un problema o suggerisci un'idea...</b> apre la pagina di KanzonasPDF su GitHub nel
browser, con moduli per segnalare un bug o proporre un'idea (per inviarli serve un account GitHub
gratuito). Descrivi cosa hai fatto e cosa è successo; per favore non allegare PDF riservati. I problemi
di sicurezza (oscuramento, password, firme) hanno lì un loro modulo privato.</li>
<li>Il download <b>KanzonasPDF-windows.zip</b> è lo stesso programma senza il file portable.txt: funziona
da qualsiasi cartella ma salva le impostazioni sul computer come la versione installata.</li>
</ul>

<h2 id="linux">KanzonasPDF su Linux</h2>
<ul>
<li><b>Installare:</b> scarica <b>KanzonasPDF-x86_64.AppImage</b> dalla pagina Releases, rendilo eseguibile (clic destro &gt; Proprietà &gt; Permessi &gt; Consenti l'esecuzione del file come programma, oppure <code>chmod +x KanzonasPDF-x86_64.AppImage</code>) e fai doppio clic su di esso. Non servono installazione né diritti di amministratore. Se non si avvia e cita FUSE o libfuse.so.2, installa FUSE 2 (Ubuntu 22.04 e Debian 12: <code>sudo apt install libfuse2</code>; Ubuntu 24.04 e successivi: <code>sudo apt install libfuse2t64</code>; Fedora: <code>sudo dnf install fuse-libs</code>) oppure avvialo con <code>--appimage-extract-and-run</code>.</li>
<li><b>Menu delle applicazioni e app PDF predefinita:</b> File &gt; Preferenze &gt; Generale &gt; <b>Aggiungi KanzonasPDF al menu delle applicazioni e usalo per aprire i PDF</b> aggiunge una voce di menu e un'icona solo per il tuo utente (in ~/.local/share) e rende KanzonasPDF l'app che apre i file PDF. Togli la spunta per rimuoverle; l'app che apriva i PDF in precedenza torna a essere quella predefinita. Se avevi creato tu una voce di menu chiamata kanzonaspdf.desktop, viene messa da parte finché c'è quella di KanzonasPDF e torna quando togli la spunta all'opzione. Alcuni desktop mostrano la nuova voce solo dopo aver chiuso e riaperto la sessione. Se sposti l'AppImage, avviala una volta dalla nuova posizione e la voce di menu la segue.</li>
<li><b>Aggiornare:</b> <b>Aggiorna ora</b> (nell'avviso di aggiornamento o in Guida &gt; Verifica aggiornamenti) scarica la nuova AppImage solo da GitHub, controlla che il suo sha256 corrisponda all'impronta pubblicata con la versione, la mette al posto del vecchio file (stesso nome e stessa posizione, così la voce di menu e l'app predefinita continuano a funzionare), chiede di salvare i documenti aperti, si chiude e avvia la nuova versione. Se tieni aperto un documento, la nuova versione parte alla successiva apertura di KanzonasPDF. Se l'AppImage si trova in una cartella che non puoi modificare, si apre invece la pagina della versione: scarica il nuovo file e sostituisci tu quello vecchio. Se avvii l'AppImage con --appimage-extract-and-run, la nuova versione viene avviata allo stesso modo. Se lo esegui dal codice sorgente, KanzonasPDF si limita a segnalarti le nuove versioni.</li>
<li><b>I tuoi file:</b> le impostazioni sono conservate in ~/.config/KanzonasPDF/KanzonasPDF.conf; firme, immagini dei timbri, certificato e backup in ~/.local/share/KanzonasPDF/KanzonasPDF (Preferenze &gt; Generale mostra entrambi i percorsi). Se chiudi la sessione o spegni il computer (o premi Ctrl+C o chiudi il terminale da cui è stato avviato KanzonasPDF) con modifiche non salvate, vengono conservate copie di backup, che ti vengono proposte all'avvio successivo, come su Windows.</li>
<li><b>Font:</b> Aggiungi testo e Modifica testo usano i font installati per fontconfig (/usr/share/fonts, ~/.local/share/fonts, ~/.fonts...): i font TrueType e OpenType vengono incorporati (anche le raccolte TrueType, .ttc, come la maggior parte dei font cinesi, giapponesi e coreani: il primo font del file); un font Type 1 no, e al suo posto si usa Helvetica. Sans Serif, Serif e Monospace usano il font che il sistema mostra per ciascuno.</li>
<li><b>Differenze rispetto a Windows:</b> la prima scelta di Visualizza &gt; Tema è <b>Come il sistema</b> (l'impostazione chiara o scura del desktop); la firma digitale usa il tuo certificato personale o un file .pfx/.p12 (non c'è l'archivio certificati di Windows); per stampare serve una stampante configurata nel sistema (CUPS); le finestre Apri e Salva sono quelle del desktop o quelle di Qt.</li>
<li><b>Rimuovere:</b> togli la spunta all'opzione delle Preferenze indicata sopra, poi elimina l'AppImage. Per rimuovere anche impostazioni e file, elimina ~/.config/KanzonasPDF e ~/.local/share/KanzonasPDF.</li>
</ul>

<h2 id="macos">KanzonasPDF su macOS</h2>
<ul>
<li><b>Installare:</b> dalla pagina Releases, scarica <b>KanzonasPDF-macos-arm64.dmg</b>. È per i Mac con Apple silicon (M1 o successivi: menu Apple &gt; Informazioni su questo Mac indica Chip Apple M...) e macOS 14.4 (Sonoma) o successivo. Non esiste ancora una versione per i Mac con processore Intel; potrebbe arrivare più avanti se viene richiesta. Apri l'immagine disco, trascina KanzonasPDF sulla cartella Applicazioni accanto, poi espelli l'immagine disco (avvia KanzonasPDF da Applicazioni, non dall'immagine disco).</li>
<li><b>La prima apertura (Apri comunque):</b> KanzonasPDF non è ancora firmato e autenticato da Apple, quindi la prima volta macOS lo blocca e avvisa che Apple non ha potuto verificare che sia privo di malware. Fai clic su <b>Fine</b> (non su Sposta nel Cestino). Poi apri Impostazioni di Sistema &gt; <b>Privacy e sicurezza</b>, scorri fino a Sicurezza, dove è indicato che KanzonasPDF è stato bloccato, fai clic su <b>Apri comunque</b>, conferma con la password o con Touch ID e fai clic ancora una volta su <b>Apri comunque</b>. Da quel momento si apre come qualsiasi altra app. macOS lo chiede di nuovo dopo l'installazione di una nuova versione. Fallo solo con un'immagine disco presa dalla pagina Releases di questo progetto; puoi verificarla prima nel Terminale con <code>shasum -a 256 KanzonasPDF-macos-arm64.dmg</code>: il risultato deve corrispondere alla riga del file in SHA256SUMS.txt della versione.</li>
<li><b>Aprire i PDF:</b> fai doppio clic su un PDF, usa Apri con nel Finder, trascina i PDF su KanzonasPDF nel Dock oppure usa File &gt; Apri. Un PDF aperto mentre KanzonasPDF è in esecuzione si apre in una nuova scheda della stessa finestra. Per aprire tutti i PDF con KanzonasPDF: seleziona un PDF nel Finder, scegli File &gt; Ottieni informazioni, scegli KanzonasPDF in Apri con e fai clic su <b>Modifica tutto...</b>.</li>
<li><b>Tasti:</b> dove questo manuale dice Ctrl, premi Comando (&#8984;), e dove dice Alt, premi Opzione (&#8997;): Ctrl+S è Comando-S, Ctrl+clic è Comando-clic, Alt+clic è Opzione-clic, Ctrl+rotellina è Comando con la rotellina del mouse. I menu, le descrizioni comando e la tabella Scorciatoie da tastiera di questo manuale mostrano i tasti del Mac. Informazioni, Preferenze (Comando-K) e <b>Esci</b> (Comando-Q, che chiude tutte le finestre chiedendo delle modifiche non salvate) si trovano nel menu KanzonasPDF, a sinistra di File. Sostituisci testo è Comando-Opzione-F (Comando-H nasconde l'app su un Mac). Per i tasti funzione (F1 questo manuale, F11 modalità CAD, F12 modalità notturna...) tieni premuto fn sulla maggior parte delle tastiere Mac; se macOS usa un tasto per sé, cambialo in Visualizza &gt; Scorciatoie da tastiera o in Impostazioni di Sistema &gt; Tastiera. Il tasto Elimina (&#9003;) elimina ciò che è selezionato.</li>
<li><b>Aggiornare:</b> KanzonasPDF ti avvisa quando c'è una nuova versione (Guida &gt; Verifica aggiornamenti); su un Mac non si sostituisce da solo. <b>Scarica</b> apre la pagina della versione: scarica la nuova immagine disco, trascina KanzonasPDF su Applicazioni e scegli Sostituisci. Le impostazioni vengono mantenute. Se macOS blocca la nuova versione, consentila di nuovo con Apri comunque (vedi sopra).</li>
<li><b>I tuoi file:</b> le impostazioni sono conservate in ~/Library/Preferences/com.kanzonaspdf.KanzonasPDF.plist; firme, immagini dei timbri, certificato e backup in ~/Library/Application Support/KanzonasPDF/KanzonasPDF (Preferenze &gt; Generale mostra entrambi i percorsi).</li>
<li><b>Font:</b> Aggiungi testo e Modifica testo usano i font in /System/Library/Fonts, /Library/Fonts e nella tua ~/Library/Fonts: i font TrueType e OpenType e le raccolte TrueType (.ttc: il primo font del file) vengono incorporati; gli altri tipi (.dfont, Type 1) no, e al loro posto si usa Helvetica.</li>
<li><b>Differenze rispetto a Windows:</b> la prima scelta di Visualizza &gt; Tema è <b>Come il sistema</b> (l'aspetto Chiaro o Scuro del Mac); la firma digitale usa il tuo certificato personale o un file .pfx/.p12 (non c'è l'archivio certificati di Windows e il portachiavi di macOS non viene usato); la barra dei menu è sempre in alto sullo schermo, quindi Visualizza &gt; Mostra barra dei menu non è disponibile; non esiste una versione portatile.</li>
<li><b>Rimuovere:</b> trascina KanzonasPDF da Applicazioni al Cestino. Per rimuovere anche impostazioni e file, elimina le due posizioni indicate sopra.</li>
</ul>

<h2 id="navigate">Spostarsi nel documento</h2>
<ul>
<li><b>Pagina successiva / precedente:</b> i pulsanti &#9664; &#9654; accanto al numero di pagina (in basso a destra
con la barra multifunzione, nella barra degli strumenti con le barre degli strumenti classiche), i tasti freccia destra /
sinistra o Page Down / Page Up, oppure digita un numero di pagina e premi Invio. <b>Home</b> ed <b>End</b> vanno alla
prima e all'ultima pagina. Gli stessi comandi sono in <b>Visualizza &gt; Vai a</b>: <b>Pagina successiva</b>,
<b>Pagina precedente</b>, <b>Prima pagina</b>, <b>Ultima pagina</b> e <b>Vai a pagina...</b> (Ctrl+G: la casella della
pagina, pronta per un numero), così li trovano anche la tavolozza dei comandi e la riga di comando CAD ("pagina
successiva", "ultima pagina").</li>
<li><b>Ingrandisci / Riduci:</b> Ctrl+Più / Ctrl+Meno, Ctrl+rotellina del mouse, il cursore dello zoom o la casella dello zoom
(digita una percentuale, dal 10% al 6400%; 25.5 e 25,5 funzionano entrambi, e anche 1,000 vale 1000%; uno
zoom non intero viene mostrato con un decimale). Con la rotellina del mouse la pagina segue subito, un po' sfocata, e
torna nitida appena la rotellina si ferma. I disegni pesanti e le scansioni grandi si completano allo stesso modo dopo
ogni zoom o scorrimento, partendo dal centro della finestra, così la finestra non resta mai ad aspettarli. Un documento
molto lungo non può arrivare a uno zoom così alto: tutte le sue pagine insieme devono restare entro la dimensione
massima che Windows riesce a disegnare.
Adatta alla larghezza (Ctrl+2), Adatta alla pagina (Ctrl+0), Dimensioni reali (Ctrl+1). I documenti si aprono con
Adatta alla larghezza, alla pagina in cui eri l'ultima volta; puoi cambiarlo in File &gt; Preferenze &gt; Avvio e apertura.
Adatta alla larghezza e Adatta alla pagina continuano ad adattare la vista quando la finestra o un pannello laterale
cambiano dimensione, finché non scegli tu uno zoom.</li>
<li><b>Miniature delle pagine</b> (F4) mostra o nasconde il pannello a sinistra.</li>
<li><b>Collegamenti nel PDF:</b> punta un collegamento per vedere dove porta. Con lo strumento <b>Mano</b>, fai clic
su di esso (il puntatore diventa una mano). Con qualsiasi altro strumento, in ogni modalità del mouse (Standard, Mano,
CAD), fai <b>Ctrl+clic</b> su di esso (tenendo premuto Ctrl sopra un collegamento compaiono una mano e la destinazione):
un clic semplice seleziona, disegna o modifica ciò su cui si trova il collegamento, così lavorando su testo, immagini
o annotazioni con un collegamento non lo apri mai per sbaglio. Un collegamento a una pagina del documento porta lì. Un
indirizzo web o e-mail chiede prima conferma, poi si apre nel browser o nel programma di posta (seleziona <b>Non
chiedere più</b> per saltare la domanda da quel momento in poi). Un collegamento a un altro PDF lo apre in una nuova
scheda; un collegamento a un altro tipo di file chiede conferma prima di aprirlo, e si aprono solo documenti, immagini,
file multimediali e disegni comuni (i collegamenti che avvierebbero un programma, uno script o un file con macro
vengono rifiutati). I collegamenti scritti da AutoCAD e da altri programmi CAD quando stampano un gruppo di tavole
funzionano così, compresi i collegamenti a file con spazi nel nome e quelli a un punto con nome nell'altro file (che si
apre in quel punto). <b>Quando il file collegato non è dove dice il collegamento</b>
(un indice creato sul computer di un'altra persona punta alla sua cartella utente, C:\\Users\\<i>nome
utente</i>\\..., oppure le cartelle sono state spostate o sincronizzate altrove), KanzonasPDF lo cerca a partire dalla
cartella del documento che stai leggendo: il nome del file del collegamento in quella cartella, oppure le sue ultime
cartelle e il nome del file (Drawings\\14854940.pdf) in quella cartella o qualche cartella più in alto. Se trova il
file, lo apre e la barra di stato indica quale file ha aperto; altrimenti il messaggio dice dove punta il collegamento
e, su Windows, quando si tratta della cartella utente di un'altra persona. Un collegamento a un file su un altro
computer (una condivisione di rete) chiede prima conferma, perché aprirlo invia a quel computer le tue credenziali di
accesso a Windows.</li>
<li><b>Trasforma qualsiasi cosa in un collegamento:</b> selezionala, fai clic con il tasto destro e scegli <b>Aggiungi
collegamento...</b>, poi digita un indirizzo web o e-mail (www.example.com va bene; https:// viene aggiunto) oppure
scegli una pagina di questo documento. Funziona con le <b>parole</b> selezionate con lo strumento Seleziona (diventano
cliccabili solo quelle parole; una selezione su più righe crea un unico collegamento), con le <b>annotazioni</b>
(timbri, caselle di testo, forme, immagini, firme) e con <b>immagini, forme e testo</b> della pagina stessa selezionati
con Modifica oggetti. <b>Aspetto</b>: <b>Sottolineatura</b> (una sottile linea blu disegnata nella pagina; la scelta
predefinita per le parole), <b>Riquadro intorno</b> o <b>Niente</b> (la scelta predefinita per immagini, forme e
annotazioni; il puntatore lo trova comunque). Le parole, l'immagine o l'annotazione in sé non cambiano.</li>
<li><b>I collegamenti restano con ciò su cui si trovano:</b> sposta, ridimensiona o ruota un'annotazione, un'immagine,
una forma o un paragrafo con un collegamento, oppure sposta con Modifica testo una riga con un collegamento, e il
collegamento (con la sua sottolineatura) si sposta insieme; eliminali e sparisce anche il loro collegamento. Un
collegamento ricorda su cosa è stato creato, quindi si sposta solo con quello: una nuvola o un riquadro disegnato
attorno a parole con un collegamento non si porta dietro il collegamento delle parole quando viene spostato o eliminato.
Dove i collegamenti si sovrappongono, Rimuovi collegamento e Modifica collegamento agiscono sul più piccolo sotto il
puntatore (il collegamento delle parole, non quello di una nuvola che le circonda). Se modifichi con Modifica testo parole con un collegamento, il collegamento resta,
compresi i collegamenti che AutoCAD scrive su un gruppo di tavole.</li>
<li><b>Nuovo testo con collegamento:</b> con lo strumento <b>Collegamenti</b> (scheda Home &gt; Inserisci, menu
Strumenti), fai clic su un punto vuoto del foglio o trascinaci sopra un riquadro: nella finestra l'opzione <b>Scrivi
questo testo sulla pagina</b> è selezionata, e il testo mostra l'indirizzo mentre lo digiti; se preferisci, digita
invece parole tue ("Il nostro sito"). Il testo viene scritto nella pagina, in blu e sottolineato, con la dimensione di
Aggiungi testo (o adattato al riquadro), e il collegamento copre esattamente quel testo. Trascina un riquadro su ciò
che è già nella pagina (un disegno, una scansione) per rendere cliccabile quell'area senza scrivere nulla.</li>
<li><b>Modificare o rimuovere un collegamento:</b> fai clic destro su di esso &gt; <b>Modifica collegamento...</b>
(dove porta, il suo aspetto e le parole che ha scritto) oppure <b>Rimuovi collegamento</b> (il collegamento e la sua
sottolineatura spariscono; le parole o l'immagine su cui si trovava restano; le parole scritte dal collegamento stesso
spariscono con lui). Anche un clic su un collegamento con lo strumento Collegamenti lo apre per la modifica, con
<b>Elimina collegamento</b>. Lo strumento Collegamenti mostra i collegamenti della pagina come riquadri blu
tratteggiati. Tutte le parti di uno stesso collegamento (su più righe) cambiano e spariscono insieme. Ctrl+Z annulla
ognuna di queste operazioni. Per un'intera serie di disegni, <b>Collega i richiami alle tavole</b> (menu Pagine) crea i
collegamenti per te a partire dai numeri delle tavole.</li>
<li><b>Panoramica:</b> strumento Mano (H; KanzonasPDF parte con questo strumento nella modalità del mouse Mano), le barre di scorrimento oppure <b>tieni premuta la rotellina del mouse e trascina</b>
(funziona con qualsiasi strumento). <b>Shift+rotellina</b> scorre sempre a sinistra e a destra, in ogni modalità del
mouse e anche quando uno scatto della rotellina altrimenti girerebbe pagina. Anche Shift+Left/Right scorre in
orizzontale.</li>
<li><b>Modalità del mouse</b> (i primi tre pulsanti della scheda Home, <b>Seleziona</b>, <b>Mano</b> e
<b>CAD</b>; il menu Visualizza; Preferenze &gt; Mouse): tre modi di lavorare, ognuno con le sue opzioni (vedi
Preferenze più avanti).
<ul>
<li><b>Mouse: Standard (freccia, la rotellina scorre)</b>: KanzonasPDF parte con lo strumento Seleziona (la freccia)
ed Esc torna a quello; la rotellina scorre e Ctrl+rotellina esegue lo zoom.</li>
<li><b>Mouse: Mano (trascina la pagina)</b>: parte con lo strumento Mano, che trascina la pagina; un clic su
un'annotazione con questo strumento la seleziona. In questa modalità il movimento libero della pagina è attivo, quindi
la Mano trascina la pagina ovunque, anche quando entra tutta nella finestra. È la modalità con cui KanzonasPDF parte la
prima volta.</li>
<li><b>Mouse: CAD (la rotellina esegue lo zoom, tienila premuta per la panoramica)</b> (F11 la attiva, e la
disattiva tornando alla modalità che avevi): come in AutoCAD, la rotellina ingrandisce e riduce attorno al cursore e,
tenendola premuta, sposti la tavola, così puoi muoverti in un disegno con qualsiasi strumento attivo. Come in
Bluebeam, tieni premuto <b>Ctrl</b> e gira la rotellina per scorrere in alto e in basso. Le pagine stanno su un'area
di lavoro aperta, il puntatore è una <b>croce</b> (tranne con la Mano), la selezione funziona come nei programmi CAD e
compare la scheda <b>CAD</b>, in primo piano, con Sposta, Copia, Ruota e gli altri comandi CAD: vedi
<b>Modalità CAD</b> più avanti.</li>
</ul>
La scelta viene ricordata. (Prima della versione 1.5 c'erano l'opzione del mouse in stile CAD e uno strumento
predefinito; le tue scelte vengono mantenute.)</li>
<li><b>Movimento libero della pagina (trascina la pagina oltre i bordi)</b> (menu Visualizza, o sotto la freccia del
gruppo Visualizzazione della scheda Visualizza): un'area di lavoro aperta intorno alle pagine, così lo strumento Mano (o la rotellina tenuta
premuta) trascina la pagina ovunque, in alto, in basso e di lato, anche quando l'intera pagina entra nella finestra,
per esempio dopo Adatta alla pagina. Il menu lo attiva o disattiva per la modalità del mouse in uso; ogni modalità
ricorda la propria impostazione (attivo in modalità Mano, disattivato in modalità Standard, attivo in modalità CAD).</li>
<li><b>Scorri una pagina per scatto della rotellina</b> (menu Visualizza): quando l'intera pagina entra nella finestra,
in altezza e in larghezza (per esempio dopo <b>Adatta alla pagina</b>), ogni scatto della rotellina passa alla pagina
successiva o precedente, centrata, invece di scorrere di poco. Appena ingrandisci tanto che un bordo della pagina esce
dalla finestra, la rotellina scorre normalmente. Tieni premuto
<b>Shift</b> per scorrere a sinistra e a destra invece di girare pagina. Attivo per impostazione predefinita; disattivalo per uno scorrimento fluido. Ogni modalità del mouse ricorda la propria impostazione. (In modalità CAD la
rotellina esegue invece lo zoom.)</li>
<li><b>Trova testo:</b> Ctrl+F, poi Invio / F3 per la corrispondenza successiva (Trova successivo) e Shift+Invio /
Shift+F3 per la precedente (Trova precedente); le frecce su e giù accanto alla casella Trova fanno lo stesso. Il contatore accanto
alla casella mostra a quale corrispondenza sei e quante ce ne sono ("3 di 120"; "Nessuna corrispondenza" quando non ce
ne sono; una parola divisa da un trattino a fine riga conta come una sola corrispondenza). La ricerca parte dalla pagina in cui sei e mostra la prima corrispondenza appena
la trova; nei documenti lunghi continua a cercare nel resto in background (il contatore indica "3 di 120+" e la barra
di stato mostra quante pagine sono state esaminate) mentre continui a lavorare. La corrispondenza corrente è ombreggiata
in arancione con una spessa cornice arancione, che resta abbastanza grande da notarla anche quando la vista è ridotta e
il testo è minuscolo. Nella vista <b>Adatta alla pagina</b>, ogni corrispondenza porta in primo piano la sua pagina
intera, centrata. Se cambi il testo
o modifichi il documento, la ricerca riparte da capo.</li>
<li><b>Sostituisci testo...</b> (menu Modifica, Ctrl+H): digita cosa trovare e con cosa sostituirlo,
seleziona <b>Maiuscole/minuscole</b> o <b>Solo parole intere</b> se serve, scegli <b>Tutte le pagine</b> o questa
pagina e fai clic su <b>Sostituisci tutto</b>. Cambia il testo del PDF stesso (non i commenti). Ogni riga che cambia
viene riscritta come fa Modifica testo, nel carattere della riga quando questo contiene i caratteri necessari, con ogni
parola nel suo stile (grassetto, corsivo, colore...). Una riga viene riscritta sul posto e non va a capo di nuovo: quando il nuovo testo finisce sopra altro
testo o oltre il bordo della pagina, Sostituisci testo indica in quali pagine (Ctrl+Z lo annulla; Modifica testo
può reimpaginare il paragrafo). Le pagine con segni di oscuramento non ancora applicati vengono saltate (indica quali).
Ctrl+Z annulla l'intera sostituzione.</li>
<li><b>Vista divisa</b> (F10) mostra una seconda vista, che scorre in modo indipendente, sotto i documenti,
o accanto a loro con <b>Affiancate</b> sulla sua barra (ricordato); trascina la barra tra le due per
dividere lo spazio. Serve solo per guardare: apporta le modifiche nella vista principale (si vedono in
entrambe). Il suo elenco mostra <b>Il documento in primo piano</b> (segue le schede) o un altro documento
aperto, per confrontare una pianta con una tavola di dettaglio o una revisione con un'altra; se quel
documento viene chiuso, mostra quello in primo piano. Spunta <b>Sincronizza</b> per scorrere e ingrandire
le due viste insieme, come Sync di Bluebeam: <b>Per numero di pagina</b> tiene la stessa pagina in
entrambe (due revisioni di una serie di tavole); <b>Per le pagine visibili</b> tiene abbinate le due
pagine mostrate quando l'hai spuntato, ai loro zoom (una pianta e il suo dettaglio), e muovere una vista
muove l'altra.</li>
<li><b>Righelli</b> (menu Visualizza, o il gruppo Visualizzazione della scheda Visualizza; Ctrl+R) mette
dei righelli lungo il bordo superiore e sinistro del documento. Misurano la pagina sotto il puntatore (o
la pagina visibile) dal suo angolo in alto a sinistra come viene mostrata, in unità della carta: la
lunghezza della pagina è la fascia più chiara, e una linea segna dove si trova il puntatore. Fai clic
destro su un righello (o sul quadrato dove si incontrano) per scegliere Pollici, Millimetri o Punti; la
posizione del puntatore nella barra di stato usa le stesse unità. La prima volta sono pollici dove il
computer misura in pollici, millimetri altrove. Restano attivi per ogni documento finché non li
disattivi.</li>
</ul>

<h2 id="reading">Leggere comodamente</h2>
<p>Il menu Visualizza e la scheda <b>Lettura</b> della barra multifunzione offrono modi per leggere un documento più
comodamente: su tutto lo schermo, una pagina o due affiancate, come testo semplice in caratteri grandi oppure ad alta
voce.</p>
<ul>
<li><b>Schermo intero</b> (menu Visualizza, Ctrl+Shift+L): solo le pagine, su tutto lo schermo: le barre degli
strumenti o la barra multifunzione, la barra dei menu, i pannelli, le schede e la barra di stato sono nascosti. Porta il
puntatore sul bordo superiore dello schermo e scende una barra sottile con pagina precedente e successiva, zoom, i
layout di pagina, Modalità lettura, Leggi questa pagina ed <b>Esci da schermo intero</b>; scompare quando il puntatore
torna giù. <b>Esc</b> esce dallo schermo intero (quando è scelto uno strumento, il primo Esc lo rilascia, come al
solito, e il successivo esce; anche in Modalità lettura), e lo stesso fa di nuovo Ctrl+Shift+L.
Tutto torna com'era. (F11, che molti programmi usano per questo, in KanzonasPDF attiva la modalità del mouse CAD, e
Ctrl+L blocca le annotazioni; Ctrl+Shift+L è libero e vicino al Ctrl+L di Acrobat.)</li>
<li><b>Presentazione</b> (menu Visualizza, F5): le pagine una alla volta, ognuna adattata a tutto lo schermo su sfondo
nero, da mostrare a un pubblico. Pagina successiva: clic, Spazio, freccia destra o giù, Page Down, Invio o N (oppure
gira la rotellina). Pagina precedente: clic destro, Backspace, freccia sinistra o su, Page Up o P. <b>Home</b> ed
<b>End</b> vanno alla prima e all'ultima pagina; digita un numero di pagina e premi Invio per andarci. <b>B</b> (o il
tasto punto) rende lo schermo nero e <b>W</b> (o il tasto virgola) bianco, per distogliere lo sguardo del pubblico
dalla diapositiva; qualsiasi tasto riporta la pagina. <b>L</b> mostra un <b>puntatore laser</b>: un punto rosso che
segue il mouse. Il puntatore del mouse si nasconde dopo due secondi di immobilità. <b>Esc</b> termina la presentazione,
e la finestra mostra la pagina su cui hai finito. Le annotazioni appaiono come sono sulla pagina (a meno che Mostra
annotazioni sia disattivato). La presentazione mostra soltanto il documento: nulla al suo interno modifica il file. Una
modifica fatta nel frattempo nella finestra (con la presentazione su un secondo schermo) compare
subito, anche Applica oscuramenti e Annulla. Premendo di nuovo F5 la presentazione torna in primo piano.</li>
<li><b>Layout di pagina</b> (menu Visualizza), ricordato per ogni documento come la pagina e lo zoom:
<ul>
<li><b>Pagina singola</b> (Ctrl+5): una pagina alla volta. Scorri fino alla sua fine (rotellina, Page Down o freccia
giù in fondo alla pagina) e la pagina successiva ne prende il posto; in cima, Page Up o la freccia su tornano alla fine
della pagina precedente.</li>
<li><b>Continua</b> (Ctrl+6): le pagine una sotto l'altra (come KanzonasPDF le ha sempre mostrate).</li>
<li><b>Due pagine</b> (Ctrl+7): due pagine affiancate, una doppia pagina alla volta, che si sfogliano come in
Pagina singola.</li>
<li><b>Due pagine continue</b> (Ctrl+8): due pagine affiancate, con le doppie pagine una sotto
l'altra.</li>
<li><b>Mostra la copertina separatamente</b>: con due pagine affiancate, la prima pagina (la copertina di un libro) sta
da sola a destra, così le pagine sinistre e destre del libro si allineano: 2 e 3, 4 e 5 e così via. Senza questa
opzione, le pagine si accoppiano 1 e 2, 3 e 4.</li>
</ul>
Con due pagine affiancate, le frecce sinistra e destra, Pagina successiva e Pagina precedente spostano di un'intera
doppia pagina; Adatta alla larghezza adatta le due pagine alla larghezza della finestra e Adatta alla pagina l'intera
doppia pagina. Ogni strumento funziona in ogni layout, e anche a schermo intero (ogni modifica è un passo che Annulla
può annullare). Con due pagine affiancate, <b>Incolla</b> (Ctrl+V) di Modifica oggetti mette ciò che hai copiato sulla
pagina sotto il puntatore, una selezione trascinata da una pagina a quella accanto si sposta lì, e <b>Sposta</b> e
<b>Copia</b> della modalità CAD la portano sull'altra pagina quando il secondo punto viene cliccato lì.</li>
<li><b>Modalità lettura</b> (menu Visualizza, Ctrl+4): il testo della pagina in un pannello laterale, reimpaginato come
semplici paragrafi in caratteri grandi che vanno a capo secondo la larghezza del pannello, per uno schermo piccolo o
per occhi stanchi. I titoli sono più grandi, come nella pagina; le immagini vengono omesse. Le colonne vengono lette in
ordine (prima la colonna di sinistra, poi quella di destra), per quanto lo permette il testo della pagina. Ingrandisci o
riduci il testo con <b>A+</b> e <b>A&minus;</b> o con Ctrl+rotellina nel pannello (l'impostazione viene ricordata).
Il pannello segue la pagina in cui sei e il PDF non viene modificato. Una pagina scansionata non ha testo da mostrare
finché non passa per Riconosci testo (OCR).</li>
<li><b>Leggi ad alta voce</b> (menu Visualizza), con le voci del computer (le voci di Windows su Windows, le voci di
sistema su macOS, Speech Dispatcher su Linux):
<ul>
<li><b>Leggi questa pagina</b> (Ctrl+Shift+V) legge la pagina in cui sei.</li>
<li><b>Leggi dal testo selezionato</b> legge dal testo che hai selezionato con lo strumento Seleziona (o dall'inizio
della pagina) fino alla fine del documento.</li>
<li><b>Leggi tutto il documento</b> (Ctrl+Shift+B) legge dalla prima all'ultima pagina.</li>
<li><b>Sospendi o riprendi la lettura</b> (Ctrl+Shift+C) e <b>Interrompi la lettura</b> (Ctrl+Shift+E).</li>
</ul>
Il testo viene letto una frase alla volta, nell'ordine in cui lo segue un lettore (prima i titoli, poi le colonne una
dopo l'altra). La frase in lettura è ombreggiata in azzurro sulla pagina e la parola pronunciata in un blu più scuro
(con le voci che indicano a quale parola sono arrivate), e la pagina scorre per seguirla. Scegli la voce e la velocità
in File &gt; Preferenze &gt; Lettura. Su Linux, installa Speech Dispatcher (il pacchetto speech-dispatcher, con una
voce come espeak-ng) se la lettura indica che la sintesi vocale non è disponibile.</li>
<li><b>Scorrimento automatico</b> (menu Visualizza, Ctrl+Shift+A): il documento scorre lentamente da solo. Le frecce
su e giù lo rallentano o lo accelerano (la velocità viene ricordata), ed Esc o di nuovo Scorrimento
automatico lo fermano. In Pagina singola e Due pagine gira anche le pagine.</li>
</ul>

<h2 id="cad">Modalità CAD: selezione e scheda CAD</h2>
<p>Nella modalità del mouse <b>CAD</b> (Visualizza &gt; Mouse: CAD, F11) KanzonasPDF seleziona e modifica come un
programma CAD. Parte con <b>Modifica oggetti</b>, che seleziona tutto insieme: le linee, il testo e le immagini del
disegno stesso e le annotazioni disegnate sopra (nuvole, linee, note...), in un'unica selezione. Sposta, Copia, Ruota,
Scala, Specchia, Allinea, Serie ed Elimina agiscono poi su tutto insieme, e un solo Ctrl+Z annulla l'operazione (il
testo del disegno si sposta soltanto: non viene copiato, ruotato, scalato né specchiato). <b>Seleziona</b> (nella
scheda CAD, oppure V quando le lettere non vanno alla riga di comando) seleziona allo stesso modo solo le tue
annotazioni o i caratteri del testo della pagina.</p>
<ul>
<li><b>Fai clic</b> su un elemento per aggiungerlo alla selezione. <b>Shift+clic</b> lo toglie.
<b>Esc</b> annulla l'intera selezione, anche subito dopo una lettera scritta per la riga di comando o un clic che ha
iniziato un riquadro di selezione. Un clic su un punto vuoto del foglio mantiene la selezione. Un'annotazione sta
sopra il disegno, quindi un clic su di essa prende l'annotazione. Un'annotazione bloccata non viene presa.</li>
<li>I <b>tasti freccia</b> spostano di poco l'intera selezione, gli oggetti del disegno e le annotazioni insieme. Fai
clic destro su un'annotazione per il suo menu, sugli oggetti del disegno per il loro.
<b>Ridimensionamento:</b> una sola annotazione selezionata mostra le sue maniglie (gli angoli e i lati di un
rettangolo, le estremità di una linea); le forme e le immagini del disegno mostrano maniglie intorno a sé; più elementi
(o annotazioni insieme a oggetti del disegno) mostrano un unico riquadro con maniglie intorno a tutti. Trascina una
maniglia per ridimensionare; un angolo mantiene le proporzioni (tieni premuto Shift mentre trascini per ridimensionare
liberamente; Shift al momento del clic toglie invece un elemento dalla selezione). L'intera modifica si annulla con un
solo Ctrl+Z.
Il testo del disegno si sposta soltanto. <b>Fai doppio clic</b> su un testo per modificarlo: il testo della pagina si
apre in Modifica testo, il testo di un'annotazione (una casella di testo, una nota, il commento di una forma) nel suo
editor.
Ciò che è selezionato viene disegnato <b>tratteggiato</b> (trattini blu su bianco, così si vede anche su una linea blu)
con piccoli <b>grip</b> blu alle estremità e agli angoli, come in AutoCAD.</li>
<li>Prima del clic, il puntatore mostra cosa prenderebbe un clic: sopra un elemento che può prendere (un'annotazione
o, con Modifica oggetti, una linea, un testo o un'immagine del disegno) la croce mostra al centro un piccolo
<b>quadratino di selezione</b>, come in AutoCAD, e quell'elemento si <b>sbiadisce</b> (viene disegnato più chiaro)
mentre il puntatore ci passa sopra, così vedi cosa prenderanno Sposta, Copia, Specchia, Scala e gli altri comandi. Un
elemento già selezionato non si sbiadisce (è tratteggiato), un'annotazione bloccata non ha né l'uno né l'altro, e
nessuno dei due compare mentre un comando chiede dei punti.</li>
<li><b>Clic, sposta, clic</b>: fai clic su un punto vuoto del foglio, sposta il puntatore (il riquadro lo segue) e fai
di nuovo clic. Da sinistra a destra è una <b>finestra blu</b> a tratto continuo: prende ciò che sta interamente al suo
interno. Da destra a sinistra è un <b>riquadro di intersezione verde</b> tratteggiato: prende tutto ciò che tocca,
compresa una linea che lo attraversa. Il primo angolo viene segnato appena fai clic, e la barra di stato chiede l'altro
angolo. Un clic rapido conta come clic anche se il mouse si è mosso un po' mentre premevi, e un nuovo clic sul primo
angolo mantiene il riquadro. Esc elimina un riquadro iniziato. Tieni premuto Shift al secondo clic per togliere invece
gli elementi. Un riquadro (o un lazo) può anche iniziare e finire nell'<b>area grigia intorno alla pagina</b>, comodo
quando la tavola è tutta coperta. Una forma piena o un'immagine che copre l'intera tavola (uno sfondo, una scansione)
qui conta come foglio vuoto: un clic su di essa avvia un riquadro, e solo una finestra attorno all'intera tavola la
prende (una forma piena anche un clic proprio sul suo bordo).</li>
<li><b>Tieni premuto il pulsante e trascina</b>: un <b>lazo</b> che segue il puntatore. Se all'inizio lo disegni verso
destra è un lazo a finestra blu (prende ciò che sta interamente al suo interno); verso sinistra, un lazo di
intersezione verde (prende ciò che tocca). Shift+lazo toglie gli elementi.</li>
<li>Con Seleziona, un riquadro o un lazo che non prende annotazioni seleziona il testo: i caratteri dentro una
finestra, o quelli toccati da un riquadro di intersezione (Ctrl+C li copia).</li>
<li>Mentre disegni un riquadro o un lazo, ciò che prenderebbe si <b>illumina</b> (in blu per una finestra,
in verde per un riquadro di intersezione), così vedi cosa otterrai prima del secondo clic o prima di rilasciare il
pulsante; una volta preso, viene disegnato tratteggiato con i grip. In un disegno molto grande si completa in un attimo mentre ti muovi.</li>
<li>Trascina ciò che è selezionato per spostarlo, come in AutoCAD: sopra un elemento selezionato il puntatore è la
freccia a quattro punte, e trascinando da lì sposti l'intera selezione (annotazioni e linee, testo e immagini della
pagina insieme; un solo passaggio di annullamento; aggancio come nel disegno). Un trascinamento che parte da un
altro punto disegna un lazo o un riquadro e non sposta nulla. Le maniglie quadrate di un'annotazione o di un
oggetto selezionato lo ridimensionano, e <b>Sposta</b> della scheda CAD sposta da un punto base.</li>
<li>Preferenze &gt; Mouse attiva o disattiva ciascuna di queste funzioni (vedi Preferenze).</li>
</ul>
<p>La scheda <b>CAD</b> (e il menu CAD) compare solo in modalità CAD. Come in AutoCAD, puoi selezionare prima e poi
avviare un comando, oppure avviare prima il comando: se non c'è nulla di selezionato, ti chiede di
<b>selezionare gli oggetti</b> (clic, riquadri, lazi come sopra), e <b>Invio</b> (o un clic destro) prosegue con ciò
che hai selezionato. Poi rispondi alla sua richiesta nella riga di comando:
fai clic su punti della pagina (si agganciano alle estremità delle linee e agli angoli come gli strumenti di disegno;
tieni premuto Alt per non agganciare), digita un valore e premi Invio, oppure fai clic su un pulsante lì. Esc (o
Annulla) interrompe un comando; il clic destro equivale a Invio. Ogni modifica si annulla con un solo Ctrl+Z.</p>
<p>Perché la modalità CAD non richieda altre schede per il lavoro di tutti i giorni, la scheda CAD contiene anche gli
strumenti più usati accanto ai suoi comandi (restano anche nelle loro schede). Gli strumenti simili condividono un
pulsante, come nella barra multifunzione di AutoCAD: fai clic sul pulsante per lo strumento che mostra, o sulla freccia
accanto per sceglierne un altro; il pulsante mostra poi l'ultimo usato (o lo strumento attivo). <b>Annotazioni</b>:
Rettangolo (freccia: Nuvola, Poligono, Maschera), Cerchio (freccia: Arco), Linea (freccia: Polilinea, Curva, Penna), Freccia, Casella di testo (freccia: Richiamo),
Timbro (freccia: Immagine, Legenda); in modalità CAD le loro scorciatoie di una lettera scrivono nella riga di comando.
<b>Misure</b>: Lunghezza (freccia: Lunghezza polilinea, Area, Angolo, Raggio, Perimetro, Volume, Conteggio,
Calibra metro a nastro), e sotto Aggancia agli oggetti, Aggancia alla griglia e Aggancia alla pagina come icone
(come nella barra di stato di AutoCAD; passa il puntatore su un'icona per vederne il nome). <b>Modifica</b>: Cancella
contenuto, Porta in primo piano (freccia: Porta avanti, Porta indietro, Porta in fondo), Allinea a sinistra (freccia:
gli altri allineamenti, Distribuisci orizzontalmente e Distribuisci verticalmente), Modifica testo (freccia: Aggiungi
testo): Modifica testo cambia le parole già presenti nella pagina, Aggiungi testo scrive nuovo testo nella
pagina.</p>
<p><b>La riga di comando</b>, lungo il bordo inferiore della finestra in modalità CAD, funziona come quella di AutoCAD.
Inizia semplicemente a digitare sopra il disegno (non serve fare prima clic nella riga) e premi
<b>Invio</b> (Spazio digita solo uno spazio, come in "adatta alla pagina"):</p>
<ul>
<li>I nomi brevi di AutoCAD: <b>M</b> Sposta, <b>CO</b> o <b>CP</b> Copia, <b>RO</b> Ruota,
<b>SC</b> Scala, <b>MI</b> Specchia, <b>E</b> Elimina (anche ERASE, DEL), <b>AL</b> Allinea,
<b>AR</b> Serie, <b>TR</b> Taglia; oppure l'inizio del nome di un comando: MOV, COP, ROT, TRI...</li>
<li>Qualsiasi altro comando con il suo nome, come lo trova la tavolozza dei comandi (Ctrl+Shift+P): "rett",
"nuvola", "adatta alla pagina", "salva con nome"... Mentre digiti, sopra la riga compare un elenco dei comandi
corrispondenti; Freccia su e Freccia giù scelgono al suo interno. Viene eseguita solo una corrispondenza sicura: il
nome intero del comando, oppure almeno tre lettere che iniziano il nome (o una delle sue parole) di quel solo comando e
di nessun altro. Accenti e maiuscole non contano. I comandi che chiudono la finestra o tolgono qualcosa dal
documento (Esci, Chiudi scheda, Elimina pagine, Rimuovi filigrane...) vengono eseguiti solo se digitati per intero, così
un EX digitato per sbaglio non chiude mai il programma. Qualsiasi altro testo non esegue nulla: la riga indica
<b>Comando sconosciuto</b> (o che corrispondono più comandi) e mantiene ciò che hai digitato, per correggerlo o per
scegliere un comando dall'elenco con Freccia su e Freccia giù e Invio. Un'impostazione attivata o disattivata
digitandone il nome indica se ora è attiva o disattivata.</li>
<li>Invio su una riga vuota ripete l'ultimo comando.</li>
<li>Mentre disegni un cerchio (dopo aver fatto clic sul centro), digita il raggio e premi Invio.</li>
<li>Mentre un comando è in corso, la riga indica cosa fare dopo e accetta ciò che digiti: un angolo, un
fattore di scala o una scelta (bastano le prime lettere del nome di un pulsante: M per Mantienili, E
per Eliminali).</li>
<li>Esc cancella ciò che hai digitato; se non hai digitato nulla, annulla il comando.</li>
<li>In modalità CAD le scorciatoie degli strumenti di una lettera (V per Seleziona, H per Mano...) scrivono invece nella
riga di comando (Preferenze &gt; Mouse, opzioni CAD: disattiva <b>Le lettere digitate sul disegno vanno alla
riga di comando</b> per mantenerle come scorciatoie degli strumenti; poi fai clic nella riga di comando per digitare un
comando); le scorciatoie Shift+lettera (Shift+M Lunghezza, Shift+A Area...) funzionano ancora finché non hai digitato
nulla, le scorciatoie con Ctrl e Alt (Ctrl+S, Ctrl+Z...) funzionano come sempre, e per gli strumenti basta digitarne
il nome ("mano", "seleziona"). Invio termina ancora un poligono o un'area in corso di disegno, e Spazio e Invio
compilano ancora il campo modulo raggiunto con Tab.</li>
</ul>
<ul>
<li><b>Sposta</b>: fai clic sul punto base, poi su dove va, in questa pagina o in un'altra: su un'altra pagina la
selezione (le linee, le immagini e il testo del disegno, insieme alle annotazioni) va lì, alla stessa distanza dal
punto cliccato lì che aveva dal punto base, come sono mostrate le pagine (anche su una pagina ruotata diversamente). I
contorni seguono il puntatore sull'altra pagina, e lì i clic si agganciano alle linee di quella pagina. Un solo
Ctrl+Z la riporta sulla sua pagina.</li>
<li><b>Copia</b>: fai clic sul punto base, poi su dove va ogni copia, quante ne vuoi, in questa pagina o in altre (come
Sposta); Invio, Esc o Fatto termina il comando.</li>
<li><b>Ruota</b>: fai clic sul punto base, poi digita l'angolo in gradi (in senso antiorario; -90 ruota in senso
orario) e premi Invio, oppure fai clic su un punto: la selezione ruota in modo che l'"est" punti lì.</li>
<li><b>Scala</b>: fai clic sul punto base, poi digita il fattore (2 = il doppio, 0.5 = la metà; da 0.001 a 1000) e premi
Invio, oppure fai clic su un punto a una distanza nota, poi sul punto alla distanza che deve diventare.</li>
<li><b>Specchia</b>: fai clic su due punti della linea di specchiatura, poi su <b>Mantienili</b> (una copia specchiata)
o su <b>Eliminali</b> (gli originali vengono sostituiti).</li>
<li><b>Elimina</b>: elimina la selezione.</li>
<li><b>Allinea</b>: fai clic su un punto della selezione e su dove va, poi su un secondo punto e su dove va; poi su
<b>Scala</b> (così coincidono anche i secondi punti) o su <b>Non scalare</b>.</li>
<li><b>Serie</b>: scegli le righe e le colonne (fino a 50 ciascuna), poi fai clic sul punto base, su dove va la copia
della colonna successiva e su dove va la copia della riga successiva (conta anche la direzione). Una serie che
creerebbe più di 20.000 oggetti chiede prima conferma (un gruppo conta tutti gli oggetti che disegna). Una serie grande (più di 20 copie di
una selezione ampia) viene creata come i programmi CAD creano i blocchi: la selezione entra nel file una volta sola,
come gruppo di disegno, e ogni copia colloca quel gruppo, così l'operazione è rapida e il file resta piccolo.
In Modifica oggetti ognuna di queste copie è un gruppo; Separa ne scompone una. Questo avviene solo per linee, forme e
immagini semplici che hanno tutte lo stesso ritaglio e stanno nello stesso livello, dove il risultato è identico a
copiare ogni oggetto; tutto il resto (gruppi, oggetti in livelli diversi) viene copiato oggetto per oggetto, il che
richiede più tempo. Le copie di una selezione di questo tipo (Copia, la copia di Specchia e serie di qualsiasi
dimensione) vengono disegnate insieme sopra gli originali, come i programmi CAD disegnano i nuovi oggetti; una
selezione distribuita su livelli o ritagli diversi tiene ogni copia subito sopra il suo originale.</li>
<li><b>Taglia</b>: come in AutoCAD, prima i <b>bordi di taglio</b>: le linee selezionate prima di TR,
o quelle che selezioni quando te lo chiede, poi Invio (Invio senza selezione: tagliano tutte le linee).
Poi fai clic sulla parte di una linea da eliminare: viene tagliata fino ai bordi di taglio più vicini che la
attraversano su ciascun lato (o fino alla sua estremità, se nessuno la attraversa da quel lato). Senza bordi di taglio
scelti, una linea che nessun'altra attraversa sparisce del tutto; con bordi di taglio scelti, una linea che non ne
attraversa nessuno resta (e il programma lo segnala). Il clic prende la linea più vicina e non
si aggancia; un clic proprio dove le linee si incrociano viene invece segnalato (fai clic un po' di lato). Fai clic
più volte; Invio, Esc o Fatto termina il comando. Taglia
le linee e le curve del disegno stesso (una curva tagliata resta una curva, tagliata esattamente dove le linee la
incrociano), le linee che un disegno rappresenta come sottili barre piene (come alcuni programmi CAD scrivono ogni
linea; le parti rimaste sono barre spesse come prima) e le annotazioni linea, freccia, polilinea, penna, arco e
curva: ciò che resta di un arco è un arco dello stesso cerchio, di una curva (una linea piegata) la stessa curva, e
una freccia mantiene la punta sulla parte all'estremità (le altre parti diventano linee semplici). Un cerchio o
un'ellisse vengono tagliati dove le linee li incrociano: ciò che resta di un cerchio è un arco, di un'ellisse una
polilinea che la segue; se meno di due linee lo incrociano, sparisce del tutto, come
in AutoCAD. Vengono tagliati anche rettangoli, poligoni e nuvole, e i loro
angoli fanno da taglio come le linee che li attraversano: un clic su un lato di un rettangolo o di una nuvola isolati
toglie quel lato da angolo ad angolo, e un altro clic ne toglie un altro. Ciò che resta è un'unica
annotazione aperta che inizia e finisce in corrispondenza dell'apertura: un rettangolo o un poligono diventa una
polilinea (stesso colore, spessore e opacità; i suoi angoli continuano a fare da taglio), e una nuvola resta una
nuvola, con i lati rimanenti identici a prima (si sposta, ruota, specchia, cambia stile e si taglia come qualsiasi
annotazione; gli altri lettori PDF la mostrano come disegnata). Un'ellisse a nuvola viene tagliata solo dove le linee
la incrociano. Un clic proprio su un angolo viene invece segnalato (fai clic sul lato, un po' lontano dall'angolo). Le
forme piene (anche una Maschera, ma non le barre sottili descritte sopra) e le immagini non vengono tagliate.</li>
</ul>
<p>In un disegno grande, la modalità CAD legge in background le linee della pagina mentre non stai facendo nulla, un
po' alla volta così la finestra risponde sempre, quindi il primo riquadro, lazo o comando parte subito; mentre un
comando lavora, il puntatore mostra il cursore di attesa. Un
riquadro a finestra prende una curva quando la curva, così come è disegnata, sta al suo interno (i suoi punti di
controllo possono sporgere).</p>
<p>Cosa non fanno i comandi: il testo del disegno si sposta (Sposta) e si copia (Copia, Serie:
come testo della pagina, ogni parola nel suo stile, come lo copia Modifica oggetti), ma ruotarlo, scalarlo o
specchiarlo lo lascia dov'è, e il programma lo segnala (si cambia con Modifica testo). Le evidenziazioni e
le altre annotazioni di testo restano sulle loro parole, quindi si possono solo spostare e copiare. Un'immagine o un
timbro specchiati continuano a leggersi nel verso giusto, e le caselle di testo ruotano di un quarto di giro alla volta.</p>

<h2 id="select">Selezionare e modificare le annotazioni</h2>
<ul>
<li><b>Strumento Seleziona (V):</b> trascina sul testo per selezionarlo, anche attraverso lo spazio tra le
pagine (resta evidenziato; vedi Copiare, tagliare e incollare più avanti). Il suo puntatore è la freccia: il cursore
di testo compare solo con gli strumenti che lavorano sul testo (Modifica testo, Aggiungi testo, Evidenzia e le
altre annotazioni di testo, Oscura) e nella casella in cui scrivi. Fai clic su un'annotazione per selezionarla,
poi trascinala per spostarla, trascina una maniglia quadrata per ridimensionarla o cambiane l'aspetto nel pannello
Proprietà.
Nella modalità del mouse <b>CAD</b>, invece, Seleziona funziona come in AutoCAD: finestre blu e riquadri di
intersezione verdi, un lazo, clic che aggiungono alla selezione, Shift per togliere, Esc per annullare la selezione,
e il trascinamento non sposta nulla (vedi Modalità CAD).</li>
<li>Con uno strumento di disegno attivo (rettangolo, linea, richiamo, ...), anche un clic su un'annotazione esistente la
seleziona, così non devi tornare alla freccia (non in modalità CAD, dove uno strumento di disegno disegna sempre). Lo
<b>strumento Mano</b> funziona allo stesso modo:
fai clic su un'annotazione (un'evidenziazione, una nota, una forma...) per selezionarla; trascina in qualsiasi altro
punto per spostare la pagina. Un'annotazione trasformata in collegamento apre invece il suo collegamento se ci fai clic
con lo strumento Mano, o Ctrl+clic con qualsiasi altro strumento (un clic semplice con Seleziona la seleziona).
Un'annotazione su un collegamento già presente nel PDF (un'evidenziazione su una voce di un sommario) viene
selezionata; fai clic sul collegamento accanto all'annotazione per aprirlo.</li>
<li><b>Contorni e riempimenti:</b> un rettangolo, un'ellisse, una nuvola, un poligono o una misura di area senza
riempimento si prende dal contorno (entro pochi pixel a qualsiasi zoom, o dall'etichetta di un'area), come in Bluebeam;
uno pieno in qualsiasi punto al suo interno. Così, con uno strumento di disegno o di misura, premendo all'interno di una
stanza delimitata da un'Area o da una nuvola disegni lì (una Lunghezza attraverso la stanza, un Conteggio, un'altra
nuvola) invece di spostare il contorno.</li>
<li><b>Più annotazioni:</b> fai Ctrl+clic su ciascuna, oppure trascina un riquadro partendo da uno spazio vuoto con lo
strumento Seleziona (Ctrl+trascinamento disegna sempre un riquadro di selezione). Ctrl+clic su un'annotazione
trasformata in collegamento apre il collegamento; per quella, trascina invece un riquadro intorno. Trascina una
qualsiasi annotazione selezionata per spostarle tutte; Canc le rimuove tutte; le modifiche in Proprietà si applicano a
tutte.</li>
<li><b>Elimina:</b> Canc o Backspace, oppure clic destro sull'annotazione &gt; <b>Elimina</b>.
<b>Modificare il testo di un commento:</b> fai doppio clic su di esso, oppure clic destro &gt; <b>Modifica testo...</b>.
Misure, timbri, legende e segnaposto di firma mostrano un testo generato da ciò che sono, quindi
non offrono Modifica testo (fai doppio clic su un timbro compilabile per cambiarne i valori); per commentarli aggiungi
una nota o una casella di testo.
Se fai clic destro su un testo evidenziato che è selezionato, il menu offre <b>Elimina evidenziazione</b>.
Nell'Elenco annotazioni (F7), fai doppio clic su una riga per modificarne il testo; fai clic destro su una riga per
<b>Modifica testo...</b> (quando il testo è modificabile) ed <b>Elimina</b>, oppure premi Canc.
L'eliminazione di un'annotazione con risposte chiede prima conferma, e porta via con sé le risposte e gli stati
(un solo Ctrl+Z li ripristina tutti).</li>
<li><b>Spostare con i tasti freccia:</b> con annotazioni selezionate (o immagini e forme selezionate con
Modifica oggetti), ogni pressione di un tasto freccia le sposta di 1 pt; <b>Shift+freccia</b> sposta di 10 pt e
<b>Ctrl+freccia</b> di 0,1 pt, per le regolazioni fini. Una serie di pressioni si annulla con un solo Ctrl+Z. Le
annotazioni legate al testo (evidenziazioni, sottolineature, barrature) restano con il loro testo. Senza nulla di
selezionato, le frecce sinistra e destra girano pagina come al solito.</li>
<li><b>Esc</b> annulla la selezione. Senza nulla di selezionato, Esc rilascia lo strumento scelto (un timbro, una
forma, una misura, Ritaglia...) e torna al tuo strumento predefinito: la Mano nella modalità del mouse Mano, Seleziona
nella modalità Standard, Modifica oggetti nella modalità CAD. Funziona anche subito dopo
che una finestra di dialogo o un clic sulla barra degli strumenti ha preso il focus della tastiera.</li>
</ul>

<h2 id="clipboard">Copiare, tagliare e incollare</h2>
<ul>
<li><b>Testo:</b> con lo strumento Seleziona, trascina sul testo; la selezione resta evidenziata.
<b>Fai doppio clic</b> su una parola per selezionarla e fai clic una <b>terza volta</b> per selezionarne l'intera riga.
Il trascinamento può superare lo spazio tra una pagina e l'altra, e include le pagine intermedie.
<b>Copia</b> (Ctrl+C) lo mette negli appunti, con una riga vuota tra una pagina e l'altra;
<b>Taglia</b> (Ctrl+X) toglie anche quelle lettere
dalla pagina (Annulla le riporta); le righe sopra e sotto mantengono le loro, anche nel testo
molto compatto. In una pagina con segni di oscuramento non ancora applicati, Taglia lascia il testo dov'è
(tagliare applicherebbe i segni): prima applicali o rimuovili. <b>Seleziona tutto il testo</b> (Ctrl+A) seleziona tutto il
testo della pagina. Esc o un clic altrove annulla la selezione.</li>
<li><b>Menu contestuale:</b> fai clic con il tasto destro sulla pagina per Taglia, Copia, Incolla, Elimina (per le
annotazioni selezionate) e Seleziona tutto il testo. Con del testo selezionato, offre anche Evidenzia, Sottolinea, Barrato,
Commenta il testo... e Segna per l'oscuramento per quel testo. Il clic con il tasto destro su un'annotazione prima la
seleziona.</li>
<li><b>Annotazioni:</b> seleziona una o più annotazioni, poi Copia o Taglia. <b>Incolla</b> (Ctrl+V) le mette
dove si trova il mouse, su qualsiasi pagina o in un altro documento aperto. Se le incolli su una pagina girata
in un altro verso (una pagina ruotata), vengono girate per apparire come erano dove le hai copiate; una casella
di testo resta comunque dritta. Un'annotazione tagliata e incollata mantiene le sue risposte e i suoi stati di revisione
(con autori e date); una copia viene incollata senza.</li>
<li><b>Duplica</b> (Ctrl+D): le copie delle annotazioni selezionate compaiono leggermente spostate, selezionate
così puoi trascinarle al loro posto. Nell'elenco delle pagine, Ctrl+D duplica le pagine selezionate; con
lo strumento Modifica oggetti, il testo, le immagini e le forme selezionati della pagina.</li>
<li><b>Il testo della pagina</b> (strumento Modifica oggetti): seleziona il testo e usa <b>Copia</b> (Ctrl+C),
<b>Taglia</b> (Ctrl+X) o <b>Duplica</b> (Ctrl+D), con i tasti, dal menu Modifica o dal menu
contestuale. <b>Incolla</b> (Ctrl+V) lo scrive nella pagina dove si trova il mouse, su qualsiasi pagina o in un altro
documento aperto, come fa Aggiungi testo: con il suo carattere (incorporato insieme al testo, così appare uguale anche se
l'altro documento non lo ha), la dimensione, il colore, il grassetto, il corsivo, il sottolineato e il barrato, la
larghezza a cui va a capo e le sue interruzioni di riga. Ogni parte incollata diventa poi un unico blocco per Modifica testo (vedi
<b>Modifica il testo che hai aggiunto</b>). Gli altri programmi ricevono solo le parole. Viene copiato anche il testo del PDF
non aggiunto qui: il testo continuo va ancora a capo alla sua larghezza, le altre righe mantengono le loro
interruzioni di riga, allineate a sinistra. Ctrl+Z annulla un incollaggio, un taglio o una duplicazione in un solo passaggio.</li>
<li><b>Le immagini e le forme della pagina</b> (strumento Modifica oggetti, o la selezione della modalità mouse
CAD): selezionale, anche insieme al testo se vuoi, e usa <b>Copia</b> (Ctrl+C) o <b>Taglia</b>
(Ctrl+X); <b>Incolla</b> (Ctrl+V) le mette nella pagina dove si trova il mouse (con il loro angolo in alto a
sinistra in quel punto), su qualsiasi pagina, su una pagina girata in un altro verso o in un altro documento aperto,
esattamente come erano: colori, spessori e tratteggi delle linee, trasparenza, immagini con le loro
maschere di trasparenza, motivi e un contorno di ritaglio che appartiene a loro (una striscia d'immagine nella
propria finestra, come le scrive "Print to PDF") o sotto cui erano disegnate. Tornano a essere contenuto della
pagina, quindi Modifica oggetti le seleziona, sposta, copia ed elimina come prima (un gruppo
resta un gruppo). Nello stesso documento, un'immagine viene memorizzata una sola volta, per quante volte la incolli, e il
contenuto incollato resta nel suo livello. In un altro documento, ogni immagine viene copiata una sola volta (se la incolli
di nuovo viene riutilizzata) e lì il contenuto non è su alcun livello (l'altro documento non ha
quel livello: mettilo su uno con il pannello Livelli, se serve). In modalità CAD, vengono incollate anche le annotazioni
selezionate insieme. Gli altri programmi ricevono un'immagine di ciò che è stato copiato (non per un
disegno grande, che richiederebbe troppo tempo). Ctrl+Z annulla un incollaggio o un taglio in un solo passaggio.</li>
<li><b>Immagini e testo da altri programmi:</b> Incolla mette un'immagine copiata (ad esempio una schermata)
come annotazione immagine, o il testo copiato come casella di testo, dove si trova il mouse. Con lo strumento Modifica
oggetti, il testo copiato va invece nella pagina stessa, con il carattere, la dimensione e il colore di Aggiungi testo.</li>
<li><b>Colori del disegno e del testo propri della pagina</b> (strumento Modifica oggetti, o la
selezione della modalità del mouse CAD): seleziona forme o testo, fai clic con il tasto destro e
scegli <b>Colore linea...</b> (il contorno delle forme selezionate), <b>Colore riempimento...</b>
(l'interno delle forme piene) o <b>Colore testo...</b> (il testo selezionato; ogni parola
mantiene carattere, dimensione, grassetto e corsivo). Ognuno è un solo passo per tutto ciò che è
selezionato (Ctrl+Z lo annulla), e la selezione resta. Un comando è disattivato quando nulla di
ciò che è selezionato lo ha (Colore riempimento per linee senza riempimento, Colore testo senza
testo); viene proposto per primo l'ultimo colore scelto per ciascuno. Le immagini e i gruppi
mantengono i loro colori (prima Separa per colorare le forme di un gruppo). Per colorare solo
alcune parole di una riga, usa Modifica testo e Colore testo in Proprietà.</li>
<li><b>Pagine:</b> sblocca l'elenco delle pagine (pulsante con il lucchetto sopra le miniature), seleziona le miniature
(Ctrl+clic aggiunge o toglie una pagina, Shift+clic seleziona una serie di pagine), poi fai clic con il tasto destro su
una qualsiasi delle pagine selezionate (l'intera selezione resta selezionata) o usa il menu Pagine:
<b>Copia pagine</b>, <b>Taglia pagine</b>, <b>Incolla pagine dopo quelle selezionate</b>, <b>Duplica pagine</b>
ed <b>Elimina pagine</b>. Dopo un clic sull'elenco delle pagine, Ctrl+C, Ctrl+X, Ctrl+V e Ctrl+A agiscono sulle
pagine, e Canc (o Backspace) elimina le pagine selezionate, dopo aver chiesto conferma. Puoi incollare
le pagine anche in un altro documento aperto. I collegamenti delle pagine copiate le seguono: un collegamento a
un'altra pagina copiata porta alla sua copia, e un collegamento a una pagina non copiata funziona ancora in un duplicato
o in un incollaggio nello stesso documento (in un altro documento viene omesso).</li>
</ul>

<h2 id="markup">Annotazioni di testo e commenti</h2>
<ul>
<li><b>Evidenzia</b> (Ctrl+Shift+H), <b>Sottolinea</b> (Ctrl+Shift+U), <b>Barrato</b>
(Ctrl+Shift+X): trascina sul testo. La selezione procede lettera per lettera.</li>
<li><b>Commento</b> (C): seleziona il testo e scrivi il commento. Il testo viene segnato (evidenziazione,
sottolineatura, barratura o linea ondulata: scegli in Proprietà) e il commento compare in una casella accanto.
Nascondi le caselle con Visualizza &gt; Mostra caselle dei commenti.</li>
<li><b>Nota adesiva</b> (N): fai clic dove va messa e scrivi.</li>
<li><b>Casella di testo</b> (T): trascina un riquadro (o fai clic) e scrivi. Ctrl+Invio termina la scrittura. Una casella di testo
è un commento (un'annotazione): chiunque può spostarla, modificarla o eliminarla in qualsiasi visualizzatore PDF finché non viene
appiattita. Il suo carattere può essere Helvetica, Times o Courier (Proprietà > Carattere): sono i caratteri che
ogni visualizzatore PDF possiede, quindi il commento appare uguale ovunque. Per scrivere testo che fa parte
della pagina, usa <b>Aggiungi testo</b> (più avanti).</li>
<li><b>Richiamo</b> (K): premi sul punto che vuoi indicare e trascina fino a dove va il testo.</li>
<li><b>Le caselle di testo e i richiami si adattano al testo:</b> il riquadro mantiene la larghezza ed è alto
quanto il suo testo, che va a capo al suo interno, quando lo crei, quando cambi il testo o la dimensione del
carattere e quando trascini un suo lato per allargarlo o restringerlo. Trascina il bordo superiore o inferiore
(o un angolo) per dargli un'altezza tua: da quel momento mantiene quel riquadro. <b>Adatta al testo</b> (clic
destro) lo rende di nuovo alto quanto il suo testo, e fa sì che uno creato prima di questa versione, o con un
altro programma, segua il suo testo da allora in poi. È la casella <b>Adatta il riquadro al testo</b> in
Proprietà, parte dello stile dello strumento (Imposta come predefinito la conserva), attiva all'inizio.</li>
<li><b>Punto</b> (B): fai clic dove va il punto, ad esempio una quota su una pianta. In
Proprietà scegli <b>Pieno</b> o <b>Solo bordo</b>, il colore, la dimensione e lo spessore del
bordo, e cosa <b>Mostra</b>: niente, il numero, un testo, oppure il numero e un testo.
<b>Posizione</b> li mette a destra, sotto, a sinistra o sopra il punto; con entrambi, il testo va
lì e il numero dall'altra parte. Oppure spunta <b>Numero dentro il punto</b> (il punto si allarga
per contenerlo; su un punto pieno il numero è bianco). Ogni nuovo punto prende il numero
successivo al più alto del documento, e così le copie (Duplica, copia e incolla); per cambiare il
numero di un punto, selezionalo e imposta <b>Numero</b>. Se il punto mostra un testo, lo scrivi
dopo il clic (Annulla non mette niente); fai doppio clic su un punto per cambiarlo. Sulle pagine
ruotate il numero e il testo restano dritti.</li>
<li><b>Nome dell'autore:</b> Modifica &gt; Nome dell'autore delle annotazioni. Viene registrato sulle tue annotazioni e
stampato sui timbri.</li>
<li><b>Controllo ortografico</b> (menu Modifica, attivo all'inizio): mentre scrivi un commento, una casella di testo, un
campo modulo su più righe, o con Modifica testo e Aggiungi testo, le parole errate ricevono una sottolineatura rossa
ondulata (inglese americano). Fai clic con il tasto destro su una di esse per le correzioni, o scegli <b>Aggiungi al
dizionario</b> per non segnalarla più (le tue parole vengono ricordate). Se il clic cade appena
accanto alla parola, le correzioni riguardano la parola in cui si trova il cursore di testo. Le abbreviazioni in maiuscolo
(HVAC) e i nomi con maiuscole all'interno (KanzonasPDF) non vengono segnalati. Fai di nuovo clic su Controllo ortografico
per disattivarlo.</li>
</ul>

<h2 id="review">Revisione dei commenti (menu Revisione)</h2>
<ul>
<li><b>Aggiungere:</b> lo strumento Commento (C) segna il testo e aggiunge un commento accanto; lo strumento Nota (N)
aggiunge una nota adesiva in qualsiasi punto.</li>
<li><b>Commento successivo</b> (Alt+Down) e <b>Commento precedente</b> (Alt+Up) scorrono tutti i
commenti e le annotazioni in ordine di lettura, pagina per pagina, selezionandoli uno alla volta. La barra di stato mostra
"Annotazione 3 di 12". Alla fine ricomincia dall'inizio.</li>
<li><b>Elenco annotazioni</b> (F7): tutte le annotazioni in una tabella, a partire da pagina 1 (fai clic sull'intestazione di
una colonna per ordinare in base a essa); filtra, fai clic per andarci, esporta in CSV (nell'ordine mostrato; se il file non si può
scrivere, perché è aperto in Excel ad esempio, un messaggio te lo segnala). Il clic su un'annotazione bloccata porta a essa senza
selezionarla, e il pulsante Elimina dell'elenco la lascia: prima sbloccala.</li>
<li><b>Mostra annotazioni:</b> togli la spunta per nascondere tutti i commenti e le annotazioni e vedere la pagina come se
non fosse annotata. Non viene eliminato nulla; rimetti la spunta per farli ricomparire. <b>Mostra caselle dei commenti</b>
nasconde solo le caselle gialle accanto al testo commentato.</li>
<li><b>Rispondi...</b> (menu Revisione, menu contestuale di un'annotazione o una riga dell'Elenco annotazioni):
risponde all'annotazione selezionata, o a una risposta, con il tuo nome (Modifica &gt; Nome dell'autore delle annotazioni...) e la data. Le risposte vengono salvate nel modo standard dei PDF (una nota "in risposta a" l'annotazione),
così Acrobat, PDF-XChange e Bluebeam le mostrano come la stessa conversazione, e le loro compaiono qui.
Una risposta non è mai un'icona sulla pagina: compare nell'Elenco annotazioni, rientrata sotto la sua annotazione,
e sopra il testo quando apri l'annotazione (con un doppio clic, o con Modifica testo...). Spostando
l'annotazione si spostano anche le sue risposte; per cambiare o rimuovere una risposta, fai clic con il tasto destro su di essa nell'Elenco annotazioni
&gt; <b>Modifica risposta...</b> o <b>Elimina risposta</b> (vengono rimosse anche le risposte a essa).</li>
<li><b>Imposta stato:</b> Accettato, Rifiutato, Annullato, Completato o Nessuno stato, e una spunta separata
<b>Contrassegnato</b> (un segno di spunta per un tuo promemoria), per le annotazioni selezionate, dal
menu Revisione o dai menu contestuali. Ogni modifica viene conservata, con chi l'ha fatta e quando (visibile
quando apri l'annotazione), e la più recente è lo stato dell'annotazione. Gli stati vengono salvati come li salva
Acrobat, quindi viaggiano con il file.</li>
<li><b>Elenco annotazioni</b>, conversazioni e stati: la colonna Risposte mostra quante risposte ha
un'annotazione; fai clic per comprimerle o espanderle. La colonna Stato mostra il suo stato (un segno di spunta
se è contrassegnata), e il secondo filtro mostra solo le annotazioni con un certo stato (o senza stato, o
contrassegnate, o non contrassegnate). Il filtro di testo trova un'annotazione anche dalle parole delle sue risposte. L'ordinamento in base a
qualsiasi colonna mantiene ogni conversazione sotto la sua annotazione.</li>
<li><b>Esporta commenti...</b> salva i commenti (le annotazioni con le loro risposte e i loro stati) come
file XFDF (il formato XML che leggono Acrobat e altri programmi; o FDF, la sua forma PDF), per inviarli
senza l'intero PDF. Il pulsante <b>Esporta commenti...</b> dell'Elenco annotazioni esporta solo le
annotazioni che mostra (filtra prima). Le immagini e i file allegati non vengono esportati: restano nel
PDF. <b>Importa commenti...</b> aggiunge i commenti di un file XFDF o FDF a un'altra copia del
documento, sulle stesse pagine, in un unico passaggio di annullamento. Un commento già presente nel documento (con lo stesso
nome) viene aggiornato se è cambiato e lasciato com'è in caso contrario, così i commenti che vanno avanti e indietro non si
accumulano, e le risposte si collegano alle annotazioni a cui rispondono. I commenti per pagine che il documento non ha
vengono saltati, e un messaggio indica quanti ne sono stati aggiunti, aggiornati e saltati, e perché. Le note scritte
in testo formattato (come le scrive Acrobat) mantengono testo e formattazione in entrambe le direzioni. Un file di commenti
non può eseguire nulla: collegamenti, script e altre azioni al suo interno vengono omessi, e un file che
dichiara entità XML o supera i 64 MB non viene letto. Un commento la cui posizione o dimensione non è
un numero utilizzabile (NaN, infinito od oltre 10 milioni di punti) viene saltato ed elencato nel
messaggio; gli altri vengono importati. Un timbro immagine in un file di commenti viene disegnato solo dalla tua
raccolta di timbri, in base al nome, mai da un'altra posizione del computer o della rete.</li>
<li><b>Riepiloga commenti...</b> crea un nuovo PDF che elenca ogni commento: pagina, tipo, autore,
data, stato e testo, con le risposte rientrate sotto. Ordinalo per pagina (con la miniatura di ogni pagina
accanto ai suoi commenti, come fa il riepilogo di Acrobat; togli la spunta da Miniature delle pagine per avere solo un elenco),
per autore, data o tipo. Si apre in una nuova scheda: stampalo (Ctrl+P) o salvalo (Ctrl+S).</li>
<li><b>Elimina commenti:</b> quelli di tutti, solo i tuoi o solo quelli di una persona, su tutte le pagine o sulla
pagina corrente. Annulla li riporta.</li>
<li><b>Appiattisci commenti:</b> rende i commenti e le annotazioni parte permanente della pagina, mentre i campi
modulo restano compilabili. (Documento &gt; Appiattisci appiattisce anche i campi modulo.) I segni di oscuramento non
ancora applicati non vengono mai appiattiti: impressi nella pagina, sembrerebbero un oscuramento con il
testo ancora sotto. Se ce ne sono, prima chiede: <b>Applicali prima</b> (il normale
Applica oscuramenti, per ogni segno del documento), <b>Lasciali come segni</b> (restano
annotazioni, il resto viene appiattito) o Annulla. Le annotazioni diventano davvero
disegno della pagina: nessun programma PDF le vede più come annotazioni. I programmi che modificano il contenuto della
pagina (Edit PDF di Acrobat, Edit Content di PDF-XChange, Modifica oggetti di KanzonasPDF) possono ancora
spostare quel disegno, come il resto della pagina, e puoi farlo anche tu (Modifica oggetti seleziona ogni
annotazione appiattita come un gruppo; Modifica testo ne cambia il testo); appiattire non è un blocco (vale lo stesso
in Acrobat e Bluebeam). Serve a inviare un file le cui annotazioni tutti vedono e stampano esattamente
come le hai fatte. Per rendere rilevabile qualsiasi modifica successiva, firma digitalmente il PDF con il blocco
contro le modifiche (certifica): i lettori PDF che verificano le firme (Acrobat, PDF-XChange, KanzonasPDF)
segnalano allora qualsiasi modifica successiva.</li>
</ul>

<h2 id="shapes">Forme, linee e penna</h2>
<ul>
<li>Rettangolo (R), Ellisse (E), Cerchio (O), Nuvola (D), Maschera, Poligono (Y), Linea (L), Freccia (A),
Polilinea (Shift+L), Arco, Curva, Penna (P). Le forme condividono un unico pulsante della barra degli strumenti: fai clic sulla sua freccia per sceglierne un'altra.</li>
<li><b>Arco</b> (come l'ARC a tre punti di AutoCAD; nella scheda CAD sotto la freccia di Cerchio): fai clic sull'inizio, su un punto
per cui passa l'arco, poi sulla fine; l'arco segue il puntatore prima dell'ultimo clic. Trascina i suoi tre punti per cambiarne la forma.</li>
<li><b>Curvare una linea o una freccia:</b> selezionala e trascina il rombo al centro: diventa una curva morbida che passa per quel
punto; le estremità restano dove sono e la punta di freccia segue la curva. Trascina di nuovo il rombo sulla linea retta per
raddrizzarla. Lo strumento <b>Curva</b> ne disegna una direttamente: fai clic sull'inizio, sulla fine, poi sul punto verso cui si piega.</li>
<li><b>Cerchio</b> (O): trascina dal centro a un punto della circonferenza. In modalità CAD, fai clic sul
centro, poi su un punto della circonferenza, oppure digita il raggio nella riga di comando e premi Invio (nell'unità
di misura della pagina, come la mostra Misure &gt; Imposta scala; funziona anche 12'-6", come pure una virgola decimale, 2,5; pollici sulla carta
quando non è impostata una scala). Crea un'annotazione ellisse, quindi Proprietà, il bordo a nuvola, lo spostamento e il
ridimensionamento funzionano come per un'ellisse.</li>
<li><b>Maschera</b>: trascina un riquadro su ciò che vuoi nascondere; viene coperto da un riquadro bianco senza contorno (come il
Wipeout di AutoCAD). Proprietà può cambiarne il colore di riempimento o dargli un contorno (Nessun bordo toglie di nuovo il contorno). Nasconde ciò che c'è
sotto sullo schermo e in stampa, ma quel contenuto resta nel file: usa Oscura per rimuoverlo
definitivamente.</li>
<li><b>In modalità CAD</b> gli strumenti che disegnano da un punto a un altro (Linea, Freccia, Rettangolo,
Ellisse, Cerchio, Nuvola, Maschera, Casella di testo, Richiamo, Lunghezza, Raggio, Calibra metro a nastro, il
riquadro della Gomma, Cancella contenuto, Cattura area, Ritaglia pagine, Collegamenti, segnaposto firma, legende) funzionano come in
AutoCAD: fai clic dove inizia, sposta il mouse (la forma segue il puntatore senza tenere premuto alcun pulsante) e
fai clic dove finisce. L'aggancio e Shift funzionano come durante il trascinamento; anche premere, trascinare e rilasciare
funziona ancora. Un clic con un leggero tremolio resta un clic. Esc o un clic con il tasto destro
annulla la forma che stai disegnando; lo zoom o lo scorrimento tra i due clic non sposta il suo primo
punto. Un clic su un'annotazione con la Gomma la elimina comunque subito, un clic su un collegamento con lo strumento
Collegamenti lo apre comunque, e due clic nello stesso punto con Casella di testo ne creano una delle dimensioni
predefinite. Nota, Timbro, Conteggio, Punto e Immagine si posizionano ancora con un solo clic.</li>
<li><b>Poligono / polilinea:</b> fai clic su ogni punto; doppio clic o Invio per terminare, Backspace per togliere l'ultimo punto,
Esc per annullare.</li>
<li>Con uno strumento di disegno, un clic su un'annotazione esistente la seleziona, e il trascinamento sposta l'annotazione o i suoi
punti, senza cambiare strumento. <b>Shift+clic su un'annotazione</b> ne inizia invece una nuova proprio lì
(per iniziare una linea alla fine di un'altra, ad esempio): nulla viene selezionato o spostato, e il
punto si aggancia all'estremità o all'angolo dell'annotazione quando l'aggancio è attivo. Il puntatore mostra la croce di
disegno mentre tieni premuto Shift. <b>In modalità CAD</b> uno strumento di disegno disegna sempre, come in AutoCAD, senza
bisogno di Shift: un clic su un'annotazione inizia lì quella nuova (agganciata alla sua estremità o al suo angolo); seleziona
le annotazioni con Modifica oggetti o Seleziona.</li>
<li><b>Tieni premuto Shift</b> mentre disegni:
  <ul>
  <li>linee, frecce, misure e segmenti di polilinea si agganciano a passi di 45&deg; (orizzontale,
  verticale o diagonale);</li>
  <li>rettangoli, ellissi e nuvole diventano quadrati e cerchi perfetti.</li>
  </ul></li>
<li><b>Tieni premuto Shift mentre ridimensioni</b> da un angolo: quadrati e cerchi restano perfetti, le altre
annotazioni mantengono le proporzioni. Shift mentre trascini l'estremità di una linea la mantiene a passi di 45&deg;.</li>
<li><b>Gomma</b> (X): fai clic su un'annotazione per eliminarla, o trascina un riquadro per eliminare tutto ciò che contiene.</li>
<li><b>Cancella contenuto</b> (Shift+E; scheda Home, menu Strumenti): come quello di Bluebeam,
trascina un riquadro per eliminare definitivamente il contenuto della pagina al suo interno: testo, immagini e linee.
Le linee e le curve che attraversano il bordo del riquadro vengono tagliate lì, così un muro che passa attraverso il riquadro
mantiene le parti esterne. Una forma piena che attraversa il bordo (un colore pieno, un tratteggio o una
sfumatura) mantiene la parte esterna e perde ciò che era dentro il riquadro; una forma interamente dentro viene
rimossa. Le annotazioni non vengono toccate (per quelle usa la Gomma, che elimina un'annotazione intera). Ctrl+Z
lo annulla. A differenza dell'oscuramento non lascia alcun riquadro nero; per le informazioni riservate usa Oscura, che
pulisce anche le copie nascoste (Cancella contenuto conserva nel file, nascosto, il contorno di un riempimento tagliato).</li>
<li><b>Cattura area</b> (Shift+P; scheda Home, menu Strumenti): come lo Snapshot di Bluebeam, trascina un riquadro per
copiare quell'area, annotazioni incluse. Ctrl+V in KanzonasPDF la incolla come annotazione immagine alle
stesse dimensioni, su qualsiasi pagina o in un altro documento, fatta del contenuto <b>vettoriale</b> originale: linee
e testo restano nitidi a qualsiasi zoom e in stampa, e puoi spostarla, ridimensionarla e ruotarla come qualsiasi
annotazione immagine. Viene conservato solo ciò che è dentro il riquadro (testo, immagini e linee all'esterno vengono
rimossi dalla copia; una linea che attraversa il bordo viene conservata intera, ma si vede solo la parte interna).
La cattura si incolla anche come immagine in Word, Excel, nelle email e in altri programmi.</li>
</ul>

<h2 id="snap">Griglia e aggancio</h2>
<ul>
<li><b>Mostra griglia</b> (menu Visualizza o barra degli strumenti) disegna una griglia sulla pagina. È solo sullo schermo:
non viene salvata nel PDF né stampata con esso.</li>
<li><b>Impostazioni griglia</b> (menu Visualizza; nella barra multifunzione sotto la freccia a destra dei pulsanti
di aggancio): la spaziatura in pollici, millimetri o punti, misurata sulla
carta, e ogni quante linee ne viene disegnata una più scura. Con uno zoom molto ridotto, vengono mostrate solo le linee
più scure.</li>
<li><b>Aggancia alla griglia:</b> i punti che disegni o trascini saltano all'intersezione della griglia più vicina.</li>
<li><b>Aggancia agli oggetti:</b> i punti saltano agli angoli, ai punti medi dei lati, ai centri e alle estremità delle
linee delle annotazioni vicine, e alle estremità delle linee, ai punti medi e agli angoli del disegno stesso (utile sulle tavole CAD).</li>
<li>Le opzioni di aggancio si trovano nel menu Visualizza e nella barra degli strumenti, nel gruppo <b>Griglia e aggancio</b> della
scheda Visualizza della barra multifunzione, nel gruppo <b>Scala e aggancio</b> della scheda Misure e nel gruppo <b>Aggancio</b>
della scheda Disponi, in Impostazioni griglia e in Preferenze &gt; Pagine e visualizzazione.</li>
<li><b>Aggancia alla pagina</b>:
i punti saltano agli angoli della pagina, ai punti medi dei suoi lati e al suo centro, e sui suoi bordi,
così un'annotazione può essere allineata esattamente al bordo o al centro della pagina.</li>
<li>Un quadrato rosa indica un aggancio a un oggetto, un cerchio verde un aggancio alla pagina, una croce blu un aggancio alla griglia.
Quando ne sono attivi diversi, prevale un oggetto vicino, poi la pagina, poi la griglia.</li>
<li>L'aggancio funziona per forme, linee, misure, poligoni, richiami, caselle di testo, timbri,
note e conteggi, e quando sposti o ridimensioni le annotazioni. La penna e gli strumenti di annotazione del testo non
si agganciano.</li>
<li><b>Trascinando un'annotazione o un'immagine</b> (anche un'immagine o un altro elemento della pagina stessa, spostato
con Modifica oggetti) si aggancia il suo intero riquadro: con Aggancia alla pagina, il suo bordo sinistro, il centro o il bordo destro
si allineano al bordo sinistro, al centro o al bordo destro della pagina, e il suo lato superiore, il centro o il lato inferiore a quelli della
pagina, ogni direzione per conto suo, e una guida tratteggiata verde mostra a cosa si è allineato (rilascia un'immagine
vicino al centro del foglio e si sistema esattamente al centro); con Aggancia agli oggetti, uno dei suoi
angoli, dei punti medi dei lati o il centro va su un punto di un'annotazione vicina o su un punto del disegno
stesso (estremità e punti medi delle linee, angoli; per gli elementi della pagina spostati con Modifica oggetti,
non i loro stessi punti dov'erano; con entrambi attivi, quello più vicino); con Aggancia alla griglia, il suo
angolo in alto a sinistra va sulla griglia.</li>
<li><b>Tieni premuto Alt</b> mentre disegni o trascini per posizionare un punto liberamente, senza aggancio.</li>
</ul>

<h2 id="properties">Colori, bordi e stili (pannello Proprietà)</h2>
<ul>
<li>Con uno strumento attivo, il pannello Proprietà (F6) imposta lo <b>stile predefinito</b> di quello strumento, salvato
per la volta successiva. Con un'annotazione selezionata, modifica <b>quell'annotazione</b>. Il titolo del pannello
dice quale: <b>Selezionato: Rettangolo</b> su una striscia blu (l'annotazione sulla pagina), oppure <b>Rettangolo:
stile predefinito</b> su una striscia ambra (le prossime che crei con lo strumento).</li>
<li><b>Ciò che hai appena disegnato resta selezionato</b>, con il suo strumento ancora scelto: cambia subito colore,
spessore o opacità in Proprietà, e trascina di nuovo per disegnare la successiva (che diventa quella selezionata).
Fai clic in un punto vuoto o premi Esc per deselezionarla; Proprietà torna allora a impostare lo stile dello
strumento. (In modalità CAD, come in AutoCAD, ciò che disegni non resta selezionato.)</li>
<li><b>Imposta come predefinito</b> (clic destro su un'annotazione): il suo stile diventa lo stile predefinito del
suo strumento, per le prossime che crei con esso (come Set as Default di Bluebeam).</li>
<li>Il cursore <b>Opacità</b> si applica quando lo rilasci, quando fai clic sulla sua guida o quando premi le frecce
della tastiera su di esso. Anche le immagini, comprese le catture incollate da Cattura area, hanno un'opacità.</li>
<li>Colore della linea, riempimento (o <b>Nessun riempimento</b>), <b>Nessun bordo</b> per riquadri e forme, colore del testo,
spessore della linea, dimensione del carattere, punte di freccia, bordo a nuvola, opacità.</li>
<li><b>Ripristina predefiniti</b> riporta uno strumento al suo stile originale.</li>
<li><b>Cassetta degli attrezzi</b> (F8, o la scheda Visualizza): i tuoi stili di annotazione preferiti, a un clic di distanza. F8
o il pulsante la apre e, quando è visibile, la richiude (se è dietro la scheda Proprietà,
viene portata davanti). Fai clic su una voce, poi
disegna: ottieni quello strumento con quel colore e quella dimensione, e le impostazioni normali dello strumento restano com'erano.
All'inizio contiene alcune voci pronte (nuvola di revisione rossa, evidenziazione gialla e verde,
freccia rossa, rettangolo blu, casella di testo rossa, richiamo giallo, timbri APPROVATO e RIFIUTATO); rinominale
o eliminale (tasto destro). Per salvare le tue: disegna un'annotazione e dalle uno stile, selezionala e fai clic su
<b>Aggiungi</b>. <b>Altro</b> &gt; Aggiungi gli strumenti iniziali riporta quelle pronte; Esporta /
Importa cassetta degli attrezzi condivide una cassetta con altre persone.</li>
</ul>

<h2 id="rotate">Ruotare le annotazioni</h2>
<ul>
<li>Seleziona una forma e trascina la <b>maniglia rotonda</b> sopra di essa. Tieni premuto Shift per passi di 15&deg;.</li>
<li>Oppure digita un angolo in <b>Rotazione</b> nel pannello Proprietà (in senso antiorario).</li>
<li>Le caselle di testo e i richiami ruotano a passi di 90&deg; (un limite delle caselle di testo PDF).</li>
</ul>

<h2 id="arrange">Allineamento, distribuzione e ordine di sovrapposizione (Disponi)</h2>
<ul>
<li>Seleziona due o più elementi, poi usa la barra degli strumenti o il menu <b>Disponi</b>: Allinea a sinistra,
Allinea al centro (orizzontalmente), Allinea a destra, Allinea in alto, Allinea i punti medi (verticalmente), Allinea in basso.
Gli elementi possono essere di qualsiasi tipo e misti: annotazioni, e linee, forme, immagini e
testo della pagina stessa selezionati con Modifica oggetti o con un riquadro di selezione in modalità CAD. Il testo della pagina viene solo spostato (il suo
riquadro mantiene le dimensioni). L'intera modifica si annulla con un solo Ctrl+Z.</li>
<li><b>Allinea rispetto a:</b> Allinea alla prima selezionata (predefinito), Allinea all'ultima selezionata,
Allinea all'intera selezione o Allinea alla pagina. Sceglilo nel menu a discesa della barra degli strumenti o in Disponi &gt;
Allinea rispetto a. La prima e l'ultima seguono l'ordine in cui hai selezionato gli elementi, sia annotazioni sia oggetti
della pagina. L'annotazione selezionata per prima ha un contorno più marcato.</li>
<li><b>Distribuisci orizzontalmente</b> / <b>Distribuisci verticalmente</b> (tre o più elementi): spazi uguali,
i due elementi esterni restano fermi.</li>
<li><b>Porta in primo piano</b> (Ctrl+Shift+]), <b>Porta avanti</b> (Ctrl+]),
<b>Porta indietro</b> (Ctrl+[), <b>Porta in fondo</b> (Ctrl+Shift+[). Con immagini o forme
della pagina stessa selezionate (strumento Modifica oggetti), questi comandi cambiano invece il loro ordine nella pagina
(vedi Modificare immagini, forme e testo del PDF).</li>
<li><b>Raggruppa</b> (Ctrl+Shift+G; menu Disponi, il gruppo Gruppo della scheda Disponi o il menu del clic
destro) fa delle annotazioni selezionate un solo gruppo: un clic su una qualsiasi le seleziona tutte, così si
spostano, si copiano, cambiano stile (Proprietà) e si eliminano insieme, e anche le copie sono un gruppo.
<b>Separa</b> (Ctrl+Alt+G) le rende di nuovo indipendenti. Raggruppare gruppi già raggruppati tra loro crea un
gruppo più grande. Allinea e Distribuisci spostano un gruppo come un solo elemento, così le sue annotazioni
mantengono il loro posto al suo interno. È il gruppo dello standard PDF (un'annotazione "in risposta" alla
prima, di tipo Group), quindi anche Acrobat le tiene insieme; in altri programmi restano annotazioni
separate.
Con linee, forme, immagini e testo del disegno della pagina selezionati (strumento Modifica oggetti, o la
modalità CAD), <b>Raggruppa</b> ne fa un unico gruppo di disegno, il tipo in cui i programmi CAD esportano i
blocchi: un clic su un punto qualsiasi, anche sul suo testo, lo seleziona tutto, e si sposta, si copia e si
elimina come un unico oggetto; Separa lo scompone di nuovo e lascia selezionati i suoi pezzi. Viene disegnato
dove si trovava l'ultimo di essi, quindi ciò che era disegnato tra di loro finisce sotto. Il suo testo viene
riscritto al suo interno con il suo carattere, la sua dimensione e il suo colore, come quando si sposta il
testo; si può ancora cercare e copiare. Modifica testo lo cambia ancora, ma una riga cambiata così esce dal
gruppo (raggruppala di nuovo, oppure prima Separa e poi Raggruppa). Le annotazioni e gli oggetti propri della
pagina non possono formare un unico gruppo (un PDF li tiene separati): se selezioni entrambi, Raggruppa è
disattivato e il suo suggerimento spiega perché.</li>
<li><b>Rifletti orizzontalmente</b> / <b>Rifletti verticalmente</b> (menu Disponi, il gruppo Gruppo o il
menu del clic destro) specchiano la selezione da sinistra a destra o dall'alto in basso attorno al suo centro,
come viene mostrata la pagina; un gruppo si riflette come un tutt'uno (ogni parte al suo posto speculare), e
anche gli oggetti della pagina selezionati con Modifica oggetti si riflettono. Specchia della modalità CAD fa lo
stesso attorno a qualsiasi linea su cui fai clic. Il testo continua a leggersi nel verso giusto.</li>
</ul>

<h2 id="objects">Pannello Oggetti e blocco</h2>
<ul>
<li>Scheda <b>Oggetti</b> (pannello sinistro, accanto a Pagine, Segnalibri e Livelli): tutte le annotazioni della
pagina corrente, dalla più in primo piano (in cima all'elenco) alla più in fondo. Fai clic su una riga per selezionare quell'annotazione anche
quando è completamente coperta da altre; Ctrl/Shift+clic ne seleziona diverse. Primo piano, Su, Giù
e Secondo piano cambiano l'ordine di sovrapposizione.</li>
<li>Colonna <b>Blocca</b>, o Disponi &gt; <b>Blocca selezionate</b> (Ctrl+L): un'annotazione bloccata si comporta
come se facesse parte della pagina. Non puoi farci clic sopra, spostarla, selezionarla o cancellarla, e trascinare
su di essa avvia invece un riquadro di selezione o una nuova annotazione. Togli la spunta da Blocca (o Disponi &gt;
<b>Sblocca tutte le annotazioni</b>) per modificarla di nuovo. Il blocco è il flag standard "locked" dei PDF, quindi
anche Acrobat e PDF-XChange lo rispettano.</li>
<li>Colonna <b>Mostra</b>: nasconde una singola annotazione (resta nel file; togliere la spunta da Mostra annotazioni nel
menu Revisione le nasconde tutte).</li>
<li>L'ultima riga, <b>Contenuto della pagina</b>, è il PDF originale stesso. Il suo testo e il suo disegno non sono
oggetti separati che puoi scegliere (una tavola CAD può contenere oltre 100.000 segmenti di linea); usa Modifica
testo per il suo testo e la scheda Livelli per i livelli CAD.</li>
</ul>

<h2 id="stamps">Timbri</h2>
<ul>
<li>Strumento Timbro (M): scegli un timbro in Proprietà (APPROVATO, BOZZA, ... o digita il tuo testo),
poi fai clic per posizionarlo.</li>
<li><b>Aggiungi il mio nome</b> e <b>Aggiungi la data</b> sono caselle di controllo separate. Se le cambi su un
timbro già posizionato, il timbro viene ridisegnato (una data aggiunta di nuovo mostra la data di oggi).</li>
<li><b>Aggiungi timbro immagine...</b> aggiunge una tua immagine (PNG/JPG) all'elenco dei timbri. Un timbro mostra
al massimo 200 caratteri del suo testo, e un timbro da compilare al massimo 20 righe.</li>
<li><b>Timbri da compilare:</b> <b>Da compilare: N. ordine / Data ordine</b> e <b>Da compilare: N. richiesta / Data
invio</b> nell'elenco dei timbri. Quando fai clic per posizionarne uno, una finestra chiede il numero e la
data (la data parte da oggi, nel formato data di Preferenze &gt; Utente). Fai doppio clic su un timbro già
posizionato per cambiarne il contenuto; si ridimensiona per adattarsi. Il suo testo di commento (nell'Elenco annotazioni, nel suo CSV
e negli altri programmi PDF) è del tipo "N. ordine PO-4471, Data ordine 26/10/2026".</li>
</ul>

<h2 id="legends">Legende</h2>
<ul>
<li><b>Legenda</b> (scheda Annotazioni, Strumenti &gt; Legenda; nella scheda CAD sotto la freccia di Timbro), come in
Bluebeam: fai clic dove va il suo angolo in alto a sinistra, o trascina un riquadro per impostarne la larghezza (il testo viene
dimensionato per adattarsi). Posiziona un riquadro che elenca i tipi di annotazioni usati: ogni riga ha un piccolo campione
disegnato nello stile proprio di quell'annotazione (colore, spessore della linea, riempimento, nuvola, punta di freccia...), la sua etichetta (il
nome dello strumento, o l'oggetto dell'annotazione quando ne ha uno, come accade spesso con le annotazioni di Bluebeam; il
nome del gruppo di un conteggio; la parola di un timbro) e quante ce ne sono. Le annotazioni dello stesso tipo in
stili diversi (nuvole rosse e nuvole blu) hanno una riga ciascuna. Le misure mostrano anche la lunghezza,
l'area o il volume totali, nelle unità della pagina (Misure &gt; Imposta scala).</li>
<li><b>Si aggiorna da sola</b> quando le annotazioni vengono aggiunte, modificate o eliminate, all'interno della stessa
modifica: Ctrl+Z annulla insieme l'annotazione e l'aggiornamento della legenda, e Ripeti li ripristina entrambi.
Non conta mai sé stessa o un'altra legenda, né le annotazioni nascoste, i segni di oscuramento, i segnaposto
firma, o le risposte e gli stati di revisione di una conversazione di commenti (fanno parte dell'annotazione
a cui rispondono). L'applicazione degli oscuramenti la ridisegna con le annotazioni rimaste (vedi Oscuramento).</li>
<li><b>Opzioni</b> (pannello Proprietà: impostale prima di posizionarla, con lo strumento Legenda scelto, o su
una legenda selezionata): <b>Titolo</b> (all'inizio Legenda; vuoto per nessun titolo), <b>Annotazioni da</b>
<b>Questa pagina</b> o <b>Tutto il documento</b> (tutte le pagine, con i totali nelle unità di questa pagina),
<b>Mostra il conteggio</b>, <b>Mostra i totali delle misure</b>, <b>Dimensione testo</b>, <b>Bordo</b> e il suo
colore, il riempimento e il colore del testo.</li>
<li>Si sposta, si ridimensiona (il testo cresce o si riduce con il riquadro), si copia, si blocca e si annulla come
qualsiasi annotazione. È un'annotazione timbro standard con un proprio aspetto, quindi gli altri programmi PDF la mostrano e
la stampano come appare qui, e Appiattisci commenti la rende parte della pagina.</li>
</ul>

<h2 id="images">Immagini e file allegati (video e altro)</h2>
<ul>
<li>Strumento <b>Immagine</b>: trascina un riquadro e scegli un'immagine (PNG, JPEG, BMP, GIF, TIFF). Viene adattata
al riquadro mantenendo le proporzioni; fai solo clic, invece, per posizionarla alle sue dimensioni naturali.
L'immagine viene incorporata nel PDF con la qualità e le dimensioni di file originali e diventa parte
della pagina stessa, come Aggiungi immagine di Acrobat: i visualizzatori PDF non possono spostarla né eliminarla. Spostala, ridimensionala,
ruotala o eliminala con <b>Modifica oggetti</b> (Shift+O), come in Acrobat e PDF-XChange. Per
un'immagine che resti un'annotazione spostabile, usa <b>Aggiungi timbro immagine...</b> con lo strumento Timbro. Allo stesso modo,
firme, sigle e date posizionate fanno parte della pagina.</li>
<li>Strumento <b>Allega file</b>: fai clic dove deve andare l'icona della graffetta e scegli un file qualsiasi, ad
esempio un video, un foglio di calcolo o una foto. Il file viene incorporato nel PDF, quindi viaggia con esso.
<b>Fai doppio clic sull'icona</b> per aprire il file con il programma che Windows usa per quel tipo (i video si riproducono
nel tuo normale lettore video). Anche Adobe Acrobat, Bluebeam e PDF-XChange possono aprirli.</li>
<li>I video non si riproducono dentro la pagina: funziona solo in pochi lettori PDF, quindi allegare
è il modo affidabile per inviare un video con un PDF. I file grandi fanno crescere il PDF di altrettanto
(ricevi un avviso oltre i 50 MB).</li>
<li><b>Allegati</b> (menu Documento): tutti i file allegati a questo PDF, compresi quelli aggiunti
da altri programmi. Apri, Salva con nome, Vai a (la sua pagina) o Elimina.</li>
<li>Per la tua sicurezza, Apri chiede prima conferma e apre solo documenti, immagini, audio,
video e disegni comuni (PDF, testo, Word/Excel/PowerPoint senza macro, immagini, MP3/MP4,
DWG/DXF...). Tutto il resto, compresi programmi, script, pagine web e file di Office con
macro, non viene aperto: usa Salva con nome e aprilo tu se ti fidi. Le copie aperte vengono
contrassegnate come scaricate da Internet, così Windows e Office le trattano con la stessa
cautela.</li>
</ul>

<h2 id="editobjects">Modificare immagini, forme e testo del PDF</h2>
<ul>
<li>Strumento Modifica oggetti (Shift+O; scheda Home, menu Strumenti), come Edit content di Bluebeam: agisce sulle
immagini (loghi, foto, scansioni) e sulle forme vettoriali (linee, rettangoli, cerchi, curve,
aree piene, linee di un disegno CAD) che fanno parte della pagina stessa, non sulle annotazioni (nella modalità mouse
CAD prende anche le annotazioni disegnate sul disegno: vedi Modalità CAD). Punta un oggetto
per vederne il contorno; fai clic per selezionarlo. Le linee vengono prese entro pochi pixel; una forma piena
viene presa in qualsiasi punto al suo interno.</li>
<li><b>Testo:</b> il testo della pagina (quello scritto da Aggiungi testo e il testo del PDF) viene selezionato un
paragrafo alla volta: fai clic su una parola per selezionarne il paragrafo, e tutto ciò che Aggiungi testo ha scritto in una
volta viene selezionato insieme. Un riquadro di selezione prende il testo solo quando non contiene immagini o forme
(così un riquadro attorno a un dettaglio del disegno ne seleziona le linee, non le etichette); Ctrl+clic aggiunge testo
a una selezione. Nella modalità mouse <b>CAD</b>, invece, la selezione funziona come in AutoCAD: una finestra
blu (da sinistra a destra) prende linee, testo, immagini e annotazioni interamente al suo interno, un riquadro intersecante
verde (da destra a sinistra) tutto ciò che tocca, testo e linee insieme; clic, riquadri e
lazo aggiungono alla selezione, Shift toglie da essa ed Esc la annulla, e i
comandi della scheda CAD la modificano (vedi Modalità CAD). Premi <b>Canc</b> (o Backspace) o tasto destro &gt; <b>Elimina</b> per rimuoverlo;
trascinalo per spostarlo (le evidenziazioni e le altre annotazioni sopra di esso si spostano insieme). Copia, Taglia, Incolla e
Duplica (Ctrl+C, Ctrl+X, Ctrl+V, Ctrl+D) lo copiano con i suoi stili come testo della pagina, anche in un'altra
pagina o documento (vedi Copiare, tagliare e incollare). Qui il testo non viene ridimensionato,
ruotato né spostato nell'ordine di sovrapposizione: cambiane le parole, il carattere e la dimensione con Modifica testo. Le immagini e le linee
sotto di esso restano. Se un altro testo lo sovrappone così da vicino che anche alcune delle sue lettere verrebbero rimosse,
KanzonasPDF chiede prima conferma. Il testo invisibile (il livello di testo riconosciuto di uno scanner) non viene selezionato.</li>
<li><b>Gruppi:</b> un gruppo di disegno che la pagina posiziona come un unico pezzo (le annotazioni appiattite e i timbri
diventano gruppi di questo tipo, e alcuni programmi esportano un intero disegno come un solo gruppo) viene selezionato, spostato, ridimensionato,
ruotato, eliminato e riordinato come un unico oggetto, come in Acrobat e PDF-XChange. Un gruppo che
riempie l'intera pagina non viene preso con un clic (afferrerebbe la tavola ogni volta che fai clic
sulla carta vuota): trascina un riquadro di selezione attorno alla pagina per selezionarlo.
Clic destro &gt; <b>Raggruppa</b> (Ctrl+Shift+G) fa delle linee, forme, immagini, testo e gruppi selezionati
un unico gruppo (vedi Allineamento, distribuzione e ordine di sovrapposizione). Un clic sul testo di un gruppo
seleziona il gruppo.
Fai clic con il tasto destro su un gruppo &gt; <b>Separa</b> per scomporlo: appare uguale, ma le sue forme e
immagini diventano oggetti separati che puoi selezionare uno per uno, e il suo testo si può cambiare con
Modifica testo. Un gruppo che contiene solo un altro gruppo (come li scrivono molti programmi) viene scomposto
in una volta sola; un gruppo con gruppi al suo interno li conserva ancora dopo un solo Separa.</li>
<li><b>Più oggetti insieme:</b> Ctrl+clic aggiunge o toglie un oggetto, oppure trascina un riquadro partendo da uno spazio vuoto
per selezionare tutto ciò che vi è interamente contenuto (Ctrl+trascinamento aggiunge alla selezione). Nei disegni CAD una
"forma" è spesso composta da molte linee separate, quindi un riquadro è il modo più rapido per prenderla.</li>
<li>Trascina la selezione per spostarla. Le forme seguono il puntatore (non sono un riquadro vuoto),
e la pagina cambia solo quando rilasci, così anche un gruppo grande resta veloce da trascinare. Rilasciala
su un'altra pagina e si sposta lì (il contorno mostra dove arriva); le annotazioni trascinate con
Seleziona o con lo strumento Mano fanno lo stesso.
Trascina una maniglia d'angolo per ridimensionarla mantenendo le proporzioni
(tieni premuto Shift per deformarla liberamente), o una maniglia laterale per renderla più larga o più alta. Ridimensionare una forma
ne scala anche lo spessore delle linee.</li>
<li>Canc (o Backspace) elimina la selezione. Fai clic con il tasto destro per Taglia, Copia, Incolla e Duplica,
Separa (gruppi), Ruota in senso orario, Ruota
in senso antiorario, i comandi dell'ordine di sovrapposizione ed Elimina e, per una sola immagine, Copia immagine
(Ctrl+V la incolla come annotazione immagine) e Salva immagine con nome.... Esc annulla la selezione.</li>
<li><b>Duplica</b> (Ctrl+D) mette copie del testo, delle immagini e delle forme selezionati leggermente
più in basso e a destra nella stessa pagina, selezionate, così puoi trascinarle al loro posto. <b>Copia</b>
(Ctrl+C), <b>Taglia</b> (Ctrl+X) e <b>Incolla</b> (Ctrl+V) li portano in un'altra pagina o in un altro documento
(vedi Copiare, tagliare e incollare).</li>
<li><b>Ordine di sovrapposizione:</b> quando gli oggetti della pagina si coprono a vicenda, selezionane uno e usa
<b>Porta in primo piano</b> (Ctrl+Shift+]), <b>Porta avanti</b> (Ctrl+]), <b>Porta indietro</b>
(Ctrl+[) o <b>Porta in fondo</b> (Ctrl+Shift+[), dal menu contestuale o da Disponi. In cima e
in fondo significano davanti o dietro a tutto ciò che c'è nella pagina, testo della pagina incluso; avanti e
indietro lo spostano oltre l'oggetto successivo con cui si sovrappone. L'oggetto mantiene colori, stile della linea e
trasparenza. Se nella posizione di partenza era ritagliato da un contorno di ritaglio, non lo è più dove
arriva.</li>
<li>Cambiano solo gli oggetti selezionati: spostamento, ridimensionamento e rotazione mantengono il loro posto
nell'ordine di disegno (il testo stampato sopra un'immagine resta sopra), i colori e gli stili delle linee, e
le immagini non vengono ricompresse, quindi la qualità non cala. Ctrl+Z annulla ogni modifica.</li>
<li>Gli oggetti dentro un oggetto raggruppato (un form XObject; usa prima Separa) e i contorni di ritaglio
non si possono selezionare con questo strumento. Nei disegni molto grandi, il primo clic su una pagina
richiede un attimo mentre la pagina viene letta.</li>
</ul>

<h2 id="edittext">Modificare il testo del PDF</h2>
<ul>
<li>Strumento <b>Aggiungi testo</b> (Shift+T; scheda Home accanto a Modifica testo, menu Strumenti): fai clic nel punto
in cui va il testo e scrivi (Invio termina, Shift+Invio inizia una nuova riga). Il testo viene scritto nella pagina
stessa, come Aggiungi testo di Acrobat: i visualizzatori PDF non possono cambiarlo, e Modifica testo lo cambia in seguito.
Scegli il font (qualsiasi font installato, più Grassetto e Corsivo), la dimensione e il colore in Proprietà. Anche la
<b>Dimensione carattere</b> si può cambiare mentre scrivi: il testo appare subito nella nuova dimensione.
I pulsanti di stile sopra la casella applicano lo stile a singole parole, come in Modifica testo (vedi <b>Grassetto, corsivo,
sottolineato e colore per singole parole</b> più avanti). La casella è larga quanto il testo che scrivi,
e si allarga e si restringe con esso. Trascina una maniglia laterale della casella per renderla
più stretta: le parole vanno a capo alla sua larghezza. Nel file vengono salvate solo le lettere
usate.
<br><b>Testo piccolo con lo zoom ridotto</b> (una tavola vista per intero): il testo che a quello zoom sarebbe troppo piccolo
da leggere, con Aggiungi testo o Modifica testo, si scrive ingrandito in una casella appena sotto la sua
posizione, e un'anteprima nella dimensione reale, con un sottile contorno tratteggiato, mostra esattamente dove va.
Trascina la casella per spostare il testo; l'anteprima la segue. Ciò che scrive Aggiungi testo viene ricordato come un unico blocco: Modifica testo lo riapre tutto (vedi
<b>Modifica il testo che hai aggiunto</b> più avanti).</li>
<li><b>Modifica il testo che hai aggiunto:</b> con lo strumento Modifica testo, fai clic su una riga qualsiasi di testo scritto con
Aggiungi testo (o incollato con Modifica oggetti): si apre tutto, in una casella larga quanto la misura a cui vanno a capo
le sue parole (larga quanto le sue righe se non andavano a capo), con le sue interruzioni di riga (Shift+Invio) e ogni
parola con il proprio stile, e il cursore sulla parola su cui hai fatto clic. Premi Invio e viene riscritto come
un unico blocco dal punto in cui iniziava, a capo alla stessa larghezza: modificarlo più volte, salvare
e riaprire il file non lo spostano. Trascina una maniglia laterale per cambiare la larghezza, o il
contorno per spostarlo. Alt+clic modifica ancora una sola riga. Il testo aggiunto con KanzonasPDF 1.9 o versioni precedenti,
o con altri programmi, si modifica come prima (un paragrafo o una riga). Se lo sposti con Modifica oggetti,
resta un unico blocco; un oscuramento applicato su alcune sue parole trasforma il resto in normale testo
della pagina.</li>
<li><b>Cambia il font o la dimensione di una riga:</b> con lo strumento Modifica testo, fai clic sulla riga: Proprietà
mostra lo stile del testo nel punto del cursore. Cambia lì <b>Dimensione carattere</b>, <b>Grassetto</b> o
<b>Corsivo</b> e la modifica si applica alle parole selezionate nella casella (che restano selezionate), oppure a
tutto il testo quando non c'è nulla di selezionato; premi Invio, che tu abbia cambiato il testo o no. Un font
scelto lì si applica a tutta la riga. La scelta vale solo per quella riga: la riga successiva su cui
fai clic riprende il proprio font e la propria dimensione (Mantieni il carattere della riga / Mantieni la dimensione della riga). Un font o
una dimensione scelti prima di fare clic su una riga si applicano a quella riga.</li>
<li><b>Elimina testo:</b> con lo strumento Modifica testo, fai clic con il pulsante destro sul testo &gt; <b>Elimina testo</b>, oppure
selezionalo con lo strumento Modifica oggetti e premi Canc (vedi sotto). Sparisce l'intero paragrafo, tutte
le righe che Aggiungi testo ha scritto in una volta; immagini e linee sotto di esso restano. Ctrl+Z lo ripristina.</li>
<li><b>Modifica un paragrafo:</b> con lo strumento Modifica testo (Ctrl+E), il contorno tratteggiato sotto il
puntatore mostra cosa modifica un clic: un intero paragrafo o una sola riga (tieni premuto Alt per una riga).
Fai clic in un punto qualsiasi di un paragrafo: l'intero paragrafo si apre in una casella della sua larghezza con il cursore sulla parola su cui hai fatto clic, e mentre
scrivi le parole vanno di nuovo a capo, come in Word. Premi Invio e il paragrafo viene riscritto con il suo font, la dimensione,
il colore e l'interlinea, e mantiene l'allineamento (a sinistra, a destra, centrato o giustificato) e una
prima riga rientrata (un rientro) o sporgente (il rientro sporgente di un paragrafo numerato). Una parola divisa da un trattino a fine riga viene riunita quando il dizionario
conosce la parola intera (spe-/cification); una parola composta con trattino (self-/consolidating) mantiene il
trattino. Il numero o il punto elenco di una voce di elenco resta dov'è e il suo testo viene riscritto.
Shift+Invio inizia un nuovo paragrafo. Trascina una maniglia laterale per renderlo più largo o più stretto, o il
contorno per spostarlo (i collegamenti sopra di esso si spostano insieme; evidenziazioni e sottolineature disegnate nella pagina restano
dov'erano, perché le parole si sono spostate al suo interno). Un paragrafo che si allunga cresce
verso il basso; non spinge in giù ciò che c'è sotto, quindi se ora si sovrappone ad altro testo o supera il
fondo della pagina, la barra di stato lo segnala (Ctrl+Z lo annulla). Ogni parola mantiene il proprio stile
durante la modifica e il ritorno a capo: font, dimensione, grassetto, corsivo, colore, sottolineatura e
barrato. La casella li mostra come nella pagina.</li>
<li><b>Grassetto, corsivo, sottolineato e colore per singole parole:</b> durante la modifica (un paragrafo, una
riga o nuovo testo con Aggiungi testo), seleziona le parole e usa i pulsanti sopra la casella:
<b>Grassetto</b> (Ctrl+B), <b>Corsivo</b> (Ctrl+I), <b>Sottolinea</b> (Ctrl+U),
<b>Barrato</b>, <b>Colore testo</b> e <b>Testo più grande</b> (Ctrl+]) / <b>Testo più
piccolo</b> (Ctrl+[), un punto alla volta (una riga con parole più grandi scende quanto serve,
così non si sovrappongono alla riga sopra). Premi di nuovo un pulsante per togliere lo stile; uno stile che hanno tutte
le parole selezionate appare premuto. Senza nulla di selezionato, il pulsante imposta lo stile di ciò che
scrivi dopo. <b>Grassetto</b>, <b>Corsivo</b> e <b>Dimensione carattere</b> in Proprietà (e il <b>Colore
testo</b> di Aggiungi testo) fanno lo stesso mentre la casella è aperta: cambiano le parole selezionate, che restano
selezionate, o tutto il testo della casella quando non c'è nulla di selezionato, e Proprietà mostra lo stile
delle parole selezionate. Non cambiano le impostazioni dello strumento per il testo successivo. Il testo scritto accanto a una parola prende
lo stile di quella parola; il testo scritto in una casella vuota prende lo stile principale del paragrafo.
<br>Grassetto e corsivo mantengono il font della riga. Si usa il vero grassetto o corsivo della stessa famiglia quando
è incorporato nel PDF o installato su questo computer (Arial Bold per Arial,
Times New Roman Italic per Times New Roman...); quando nessuno dei due lo ha, lo stesso identico font viene disegnato più spesso (grassetto) o
inclinato (corsivo), come fa Word per un font senza grassetto o corsivo. Solo i caratteri che il font
non sa scrivere affatto passano a un altro font, una parola alla volta. Togliere il grassetto da una parola scritta in un
font grassetto richiede lo stile normale di quel font (incorporato o installato); senza di esso la parola resta
in grassetto.
<br>Sottolineature e barrature vengono disegnate nella pagina nel colore delle parole, una linea
per ogni riga di testo, e si spostano e vanno a capo con le loro parole quando il paragrafo viene modificato di nuovo. Una
linea sottile disegnata appena sotto (o attraverso) una serie di parole e lunga quanto esse, come l'esportazione PDF di Word
scrive le sottolineature, viene letta come loro sottolineatura; una linea più lunga, il bordo di una tabella o la riga di
un cartiglio restano dove sono.</li>
<li><b>Cosa conta come paragrafo:</b> righe di una sola dimensione, una sotto l'altra con un'interlinea
regolare, allineate su un lato (o centrate), che vanno a capo come testo continuo. Termina con la sua
ultima riga corta, quindi i passaggi numerati e i paragrafi senza spazio tra loro sono ciascuno
a sé; una riga che inizia con un numero o un punto elenco ("2.", "(b)", "1.Turn", un simbolo)
ne inizia uno nuovo. Tutto il resto si
modifica una riga alla volta: righe singole; etichette dei disegni, cartigli e testo delle quote; celle di tabelle
e di abachi; una colonna accanto a un'altra colonna; un titolo (la sua dimensione è diversa da quella del testo
sotto); le voci di elenco, ciascuna a sé (anche un elenco di voci di una riga i cui punti elenco sono
disegnati, dove ogni riga è una frase a sé); testo scansionato e testo girato di lato, e pagine
ruotate.</li>
<li><b>Modifica una sola riga:</b> fai <b>Alt+clic</b> su una riga per modificare solo quella riga, anche dentro un
paragrafo. <b>Premi su una riga e trascina</b> per spostarla (testo e font restano come sono,
così come lo stile e la sottolineatura di ogni parola).
Durante la modifica di una riga: il cursore va dove hai
fatto clic, e la riga riceve un contorno tratteggiato con maniglie, come un oggetto selezionato. Scrivi la
modifica; trascina il contorno per spostare il testo, trascina una maniglia per cambiare la larghezza a cui va a capo il testo
(le lettere mantengono la loro dimensione). Premi Invio (o fai clic altrove)
per terminare, Shift+Invio per iniziare una nuova riga, Esc per annullare. Anche il salvataggio, la chiusura del documento,
Annulla o un cambio di pagina terminano una modifica in corso, così il testo scritto non va mai perso.
Il testo di lato (girato sulla pagina, o su una pagina ruotata) si apre in una casella diritta sopra il
centro della riga, così è facile scrivere, con il cursore nel punto della riga in cui hai fatto clic; quando
hai finito il testo resta girato sulla pagina.</li>
<li>Evidenziazioni, sottolineature, barrature, commenti e note su quella riga si spostano con essa.</li>
<li>Le parole che la pagina disegna invisibili (le parole di un livello OCR in una riga, una parola nascosta) restano
invisibili quando la loro riga o il loro paragrafo viene modificato, trascinato, cambiato da Sostituisci testo o spostato con
un disegno; la casella le mostra sbiadite. Le parole trasparenti mantengono la loro opacità.</li>
<li>Si usa il font originale quando è incorporato o installato e contiene tutti i caratteri che hai
scritto; altrimenti il font standard più simile, o, per i caratteri che questi non sanno scrivere (greco come
&Omega; &Delta;, simboli, cinese e altre scritture), un font Unicode integrato. Vengono salvate solo le lettere
usate, così i file restano piccoli. La barra di stato indica quale font è stato usato. Se nessun
font ha un simbolo che hai scritto o che proveniva dal PDF (un segno meno, un simbolo di diametro, uno
spazio stretto invisibile...), si prova un font installato più completo come Segoe UI, poi si usa un carattere simile
(- per il segno meno, &Oslash; per il simbolo di diametro, uno spazio normale per uno
invisibile). I caratteri che non si possono scrivere affatto, come le emoji, vengono indicati in un messaggio, e
non viene cambiato nulla. Il testo scritto da destra a sinistra (ebraico, arabo) non si può ancora modificare, spostare o
aggiungere (risulterebbe nell'ordine sbagliato): un messaggio lo segnala, e non viene cambiato nulla.
Una riga di una
pagina che ha ancora segni di oscuramento non applicati non si può modificare finché non li applichi o li rimuovi.</li>
<li><b>Pagine scansionate</b> (un'immagine del foglio con il testo riconosciuto sopra, dall'OCR dello
scanner o da Riconosci testo): Modifica testo, Trova e sostituisci e lo spostamento di una riga cambiano anche
l'immagine. Le vecchie parole vengono coperte con il colore della carta, e il nuovo testo viene scritto
in modo da somigliare alla scansione: KanzonasPDF disegna le vecchie parole in ogni font standard e nei font
installati più comuni (Arial, Calibri, Times New Roman, Courier New e altri), normale, grassetto e
corsivo, le confronta con le lettere scansionate e usa il più simile, alla dimensione e sulla
linea di base adatte, nel colore dell'inchiostro della scansione (grigio, blu...). L'editor si apre in quel font
e in quella dimensione, e la barra di stato indica cosa è stato abbinato ("Adattato alla scansione: Helvetica Bold,
11 pt"). Un font o una dimensione scelti in Proprietà hanno comunque la precedenza. Le linee di modulo sotto il testo e
il testo delle righe sopra e sotto restano come sono, e una casella di controllo con cui inizia il testo della scansione
resta nell'immagine finché il nuovo testo inizia ancora con essa. Il
carattere tipografico scansionato non si può riconoscere da un'immagine, quindi il risultato è il font disponibile più simile;
se il testo riconosciuto non corrisponde alle lettere (l'OCR le ha lette male), si usa Helvetica alla
dimensione delle lettere, e la barra di stato lo segnala. La nuova riga è vero testo: ricerca, copia e Modifica
testo funzionano su di essa, e modificarla di nuovo mantiene il suo font.</li>
</ul>

<h2 id="measure">Misurazioni</h2>
<ul>
<li>Imposta prima la scala del disegno: Misure &gt; <b>Imposta scala</b> (predefinite come 1/4" = 1'-0",
1:100), oppure <b>Calibra metro a nastro</b> (Calibra sulla barra multifunzione): trascina lungo una dimensione nota e digita la sua lunghezza
reale. KanzonasPDF legge le note di scala scritte sulla tavola (SCALE: 1/4" = 1'-0", 1" = 20',
1:50, NTS, nel cartiglio o sotto i titoli dei dettagli): Imposta scala le propone come <b>Scala
indicata sulla tavola</b>, già scelta per te quando il cartiglio ne ha una, e la barra di stato
riporta ciò che dice la tavola finché non è impostata nessuna scala. La scala di una pagina la accompagna: le copie fatte
con Duplica pagine, Copia pagine e Incolla, Estrai pagine, Inserisci pagine da file e Combina
file la mantengono.</li>
<li>La scala della pagina corrente è sempre visibile: in caratteri grandi sotto "Imposta scala" nel
gruppo <b>Scala della pagina</b> della scheda Misure (1/4" = 1'-0", 1:100...) e in grassetto a destra della barra di stato. Una pagina
senza scala mostra lì <b>Scala non impostata</b> in rosso, e le sue misure sono nelle dimensioni del foglio
(pollici sulla tavola). Fai clic su uno dei due per aprire Imposta scala; entrambi seguono la pagina in cui ti trovi e
cambiano non appena una scala viene impostata, calibrata o annullata. La prima misurazione su una pagina senza
scala (una volta per pagina) mostra anche un banner sopra la pagina che lo segnala, con un pulsante <b>Imposta scala...</b>;
scompare quando la pagina riceve una scala, o con il suo pulsante di chiusura. Conteggio e Angolo
non dipendono dalla scala e non fanno comparire il banner.</li>
<li><b>Mostra barra della scala</b> (menu Visualizza, menu Misure, la piccola icona accanto a "Imposta scala" nel
gruppo Scala della pagina della scheda Misure, e
Preferenze &gt; Pagine e visualizzazione): disegna una scala grafica in basso a sinistra di ogni pagina
che ha una scala: segmenti alternati bianchi e neri con numeri tondi nelle unità del
disegno (0 5' 10' 15' 20' per piedi e pollici, 0 1 2 3 4 m per i metri; i millimetri passano ai
metri per le lunghezze grandi). Sceglie una lunghezza adatta allo zoom, così resta di una dimensione utile mentre
ingrandisci e riduci, e si trova su una piastra propria, così si legge su disegni chiari e scuri
(scura in modalità notte). È solo a schermo: non viene mai stampata, esportata o salvata nel
file. La tua scelta viene ricordata.</li>
<li><b>Leggi le scale dai cartigli</b> (menu Misure, scheda Misure): per un intero set in una volta,
ogni pagina riceve la scala indicata dal proprio cartiglio; le pagine segnate come non in scala o senza
nota restano come sono e vengono elencate. Fidati ma verifica: una tavola stampata in formato ridotto (una
24x36 su carta 11x17) riporta ancora la scala originale, e niente sulla pagina lo rivela. Misura
una dimensione nota dopo aver letto le scale, e usa Calibra metro a nastro se non torna.</li>
<li><b>Lunghezza</b> (Shift+M), <b>Lunghezza polilinea</b>, <b>Area</b> con perimetro (Shift+A) e
<b>Conteggio</b> (Shift+C, con gruppi con nome). I valori si aggiornano quando modifichi l'annotazione o cambi
la scala. Un indicatore di Conteggio copiato con Duplica (Ctrl+D) o con copia e incolla prende il numero
successivo del suo gruppo.</li>
<li><b>Quota</b> (Shift+D; scheda Misure, gruppo "Altro", il menu Misure e il pulsante Misure della scheda CAD),
come la quota di Bluebeam e la quota allineata di AutoCAD: fai clic sui due
punti da misurare, poi sposta il puntatore e fai clic dove va la linea di quota (nella
modalità mouse Standard puoi anche trascinare dal primo punto al secondo, poi fare clic). Disegna
due linee di estensione dai punti, una linea di quota con le frecce tra di esse
e la lunghezza sopra la linea, nella scala e nell'unità della pagina, come la misura Lunghezza; il testo
si legge diritto anche sulle pagine ruotate. Esc annulla. Trascina i suoi punti di presa per modificarla: i due
punti misurati (misurata di nuovo) o il punto di presa al centro della linea di quota (più vicina o
più lontana dai punti). Colore della linea, spessore, <b>Punta freccia</b> (chiusa, aperta, barra, punto o
nessuna) e dimensione del testo sono in Proprietà. È una linea di quota PDF standard, quindi anche gli altri visualizzatori
PDF la mostrano.</li>
<li>Altre misure (scheda Misure, gruppo "Altro", e il menu Misure):
<b>Angolo</b>: fai clic su un'estremità, sul vertice, poi sull'altra estremità; mostra l'angolo in gradi.
<b>Raggio</b>: trascina dal centro di un cerchio al suo bordo; disegna il cerchio e mostra il
raggio (R) e il diametro (&Oslash;).
<b>Perimetro</b>: fai clic sui vertici, poi fai doppio clic o premi Invio; mostra la lunghezza del contorno.
<b>Volume</b>: fai clic sui vertici dell'area, poi fai doppio clic o premi Invio; mostra area
&times; profondità. Imposta la <b>Profondità</b> nel pannello Proprietà, nell'unità della scala della pagina (piedi
quando la scala è in piedi e pollici); cambiarla aggiorna la misura selezionata.</li>
<li><b>Riepilogo misure</b> somma tutto ed esporta in CSV.</li>
<li><b>Spazio</b> (scheda Misure, gruppo "Altro", il menu Misure e il pulsante Misura della scheda CAD),
come gli Spaces di Bluebeam: un'area con un nome in una tavola (una stanza, una zona, un piano). Fai clic su
ogni angolo, doppio clic o premi Invio, e digita il suo nome (viene proposto Spazio 1, Spazio 2...). È un
poligono blu trasparente con il suo nome scritto dentro sullo schermo; colore, contorno e trasparenza sono in
Proprietà, e i suoi grip spostano gli angoli come quelli di un poligono. Fai clic sul contorno per
selezionarlo: un clic all'interno disegna o seleziona ciò che c'è nella stanza. Per rinominarlo, fai clic
destro &gt; <b>Rinomina spazio...</b>. Ogni annotazione il cui centro è dentro uno spazio appartiene a quello
spazio (al più piccolo, dove gli spazi si sovrappongono): l'Elenco annotazioni lo mostra nella colonna
<b>Spazio</b> e, quando il documento ha degli spazi, ha un elenco per mostrare le annotazioni di un solo spazio
(con Tipo impostato su Conteggio, in alto compare il suo conteggio, come "12 di 40"). Sposta un'annotazione
dentro o fuori e il suo spazio la segue. Gli altri programmi PDF mostrano uno spazio come un poligono con il
suo nome come commento.</li>
</ul>

<h2 id="pages">Pagine</h2>
<ul>
<li><b>Ruota pagina a sinistra / Ruota pagina a destra:</b> Ctrl+Shift+Meno / Ctrl+Shift+Più.</li>
<li><b>Ritaglia pagine</b> (menu Pagine, scheda Pagine, menu Strumenti): trascina un riquadro attorno a ciò che vuoi tenere, poi
scegli <b>Questa pagina</b> o <b>Tutte le pagine</b> (sulle altre pagine lo stesso riquadro è misurato dal loro
angolo superiore sinistro). Cambia solo l'area visibile; non viene eliminato nulla, quindi <b>Rimuovi ritaglio...</b>
(menu Pagine, scheda Pagine) mostra di nuovo la pagina intera, su questa pagina o su tutte. Ctrl+Z annulla
entrambe le operazioni. Le annotazioni restano dove sono sulla pagina, anche quando le modifichi dopo.</li>
<li><b>Aggiungi spazio attorno alla pagina...</b> (menu Pagine, scheda Pagine): ingrandisce la pagina sui lati che
scegli, così come viene mostrata: scrivi quanto aggiungere a <b>Sinistra</b>, in <b>Alto</b>, a <b>Destra</b> e in
<b>Basso</b> (in pollici, millimetri o punti) e scegli le pagine (quella corrente, tutte o un elenco come 1-3, 5). Il
disegno, le annotazioni, i collegamenti e i campi modulo restano esattamente dove sono sulla pagina; il nuovo spazio
è pagina bianca. È pagina vera: ciò che ci metti (commenti, o altre tavole incollate con Cattura area per formare un
unico disegno combinato) si vede in qualsiasi programma PDF e viene stampato. Ctrl+Z lo annulla; <b>Ritaglia
pagine</b> toglie di nuovo lo spazio. Una pagina può misurare al massimo 200 pollici per lato (il limite del PDF).</li>
<li><b>Dimensione dell'elenco pagine:</b> trascina il bordo del pannello Pagine per restringerlo quanto vuoi; le
miniature si riducono per adattarsi (il pulsante del lucchetto mostra allora solo Bloccato / Sbloccato). Le schede che non ci stanno
scorrono di lato.</li>
<li><b>Blocco dell'ordine delle pagine:</b> il pulsante del lucchetto sopra le miniature (bloccato per impostazione predefinita) protegge
l'ordine delle pagine: finché è bloccato, nulla sposta, aggiunge o rimuove pagine, che sia il trascinamento,
il menu Pagine, la barra multifunzione o una scorciatoia (Sposta pagina su / giù, Elimina pagine, Inserisci pagine, Inserisci
pagina vuota, Taglia, Incolla e Duplica pagine). Se ne usi uno, ti viene chiesto se sbloccare prima.
Copiare, ruotare ed estrarre pagine funziona anche con il blocco attivo.</li>
<li><b>Riordina:</b> sblocca l'elenco delle pagine, poi trascina le miniature (più pagine selezionate si spostano
insieme, e Ctrl+Z annulla l'intero trascinamento). Per portare una pagina in un punto che non si vede, tienila
vicino alla parte alta o bassa dell'elenco, oppure appena sopra o sotto di esso: l'elenco scorre, tanto più
veloce quanto più ti allontani. Oppure usa Sposta pagina su / Sposta pagina giù
(Ctrl+Shift+Up / Down; nella scheda Pagine, sotto la freccia del gruppo Organizza).</li>
<li><b>Combina file</b> (File &gt; Combina file..., o scheda Pagine &gt; Combina): crea un
nuovo PDF da più file. Aggiungi i PDF (Aggiungi file..., o trascinali nell'elenco da Esplora file); il
documento aperto è già nell'elenco. Trascinali, o usa Sposta su / Sposta giù / Ordina per nome, per
impostare l'ordine, dall'alto in basso. Con "Aggiungi un segnalibro per ogni file" selezionato, ogni file riceve un
segnalibro con il suo nome e mantiene i propri segnalibri sotto di esso (ognuno porta ancora al suo punto
della pagina, con il suo stile). Fai clic su Combina..., scegli un nome,
e il PDF combinato si apre. Per i file protetti da password viene chiesta la password. I file originali
non vengono modificati, e il nuovo PDF non può sostituirne uno.</li>
<li>Combina file accetta anche immagini (JPG, PNG, TIFF, BMP, GIF, WebP): ognuna diventa una pagina.
<b>Crea PDF da immagini...</b> (menu File, scheda Pagine &gt; gruppo Crea) parte dalle immagini: sceglile, mettile
in ordine e fai clic su Crea.... Con "Metti ogni immagine su una pagina Letter" selezionato (impostazione
predefinita), ogni immagine viene adattata a una pagina Letter orientata secondo l'immagine (orizzontale per le immagini
larghe); deselezionalo perché ogni pagina abbia le dimensioni dell'immagine. Le foto del telefono risultano diritte,
le foto JPEG non vengono ricompresse (nessuna perdita di qualità), e ogni pagina di una scansione TIFF multipagina
diventa una pagina. Seleziona "Rendi le immagini ricercabili (riconoscimento del testo, OCR)" (qui e in Combina
file) per le immagini di testo, come scansioni e foto di documenti fatte con il telefono: quando il PDF si apre,
il testo delle pagine create dalle immagini viene riconosciuto, come fa Riconosci testo (OCR), e il PDF viene
salvato con esso, così le sue parole si possono cercare e selezionare (le pagine PDF aggiunte restano come
sono). La scelta viene ricordata.</li>
<li><b>Inserisci pagine da file</b> (menu Pagine, scheda Pagine) inserisce PDF e immagini (JPG, PNG,
TIFF, BMP, GIF, WebP; puoi sceglierne più di uno insieme), nell'ordine scelto, dopo la pagina corrente, alla
fine o all'inizio, come un unico passaggio di annullamento. Ogni immagine diventa una pagina delle dimensioni della pagina
precedente, orientata secondo l'immagine. Senza nulla di aperto, crea da essi un nuovo PDF non
salvato.</li>
<li><b>Sostituisci pagine</b> (menu Pagine; scheda Pagine, nella freccia accanto a Estrai) mette una nuova
revisione delle tavole al posto delle vecchie e mantiene tutto ciò che vi era stato aggiunto (Sostituisci pagine di Acrobat,
lo slip sheeting di Bluebeam). Scegli il PDF della nuova revisione, poi indica le
pagine per numero (qui le pagine 3-5 sostituite dalle pagine 1-3 del nuovo file, abbinate in ordine) oppure
scegli <b>Abbina le tavole per numero di tavola</b>: i numeri di tavola vengono letti dai cartigli di
entrambi i file (come li legge Collega i richiami alle tavole) e ogni pagina qui viene abbinata alla pagina del nuovo file
che ha lo stesso numero. Controlla l'elenco prima di fare clic su Sostituisci: correggi un abbinamento
digitando la pagina del nuovo file in "Sostituita dalla pagina", o svuota il campo per lasciare la pagina com'è.
Le pagine qui senza corrispondenza restano invariate, e le tavole del nuovo file che non corrispondono a nessuna pagina sono
elencate sotto l'elenco, così lo sai. Cambia solo il disegno della pagina (il contenuto, i riquadri di pagina
e la rotazione): la pagina stessa resta, quindi restano le sue annotazioni, i collegamenti, i campi modulo, la scala e i segnalibri,
e i segnalibri e i collegamenti da altre pagine continuano a portare lì. Quando una nuova pagina ha un'altra
dimensione, scegli se le annotazioni vanno <b>ridimensionate in base alla nuova pagina</b> (insieme al testo e allo spessore delle linee;
deformate se le proporzioni sono diverse; un ridimensionamento uniforme adatta anche la scala di misura della pagina e
il suo nome, 1/4" = 1'-0" diventa 1/2" = 1'-0" su una tavola di dimensioni doppie) o <b>mantenute nella stessa posizione</b>,
misurata dall'angolo superiore sinistro. Le misure vengono ricalcolate quando ciò che misurano è cambiato
(la nuova pagina ha una sua scala, o le annotazioni sono state deformate o ridimensionate su una pagina senza
scala). Un segnalibro a un punto della pagina porta allo stesso punto del nuovo disegno, come vengono posizionate le annotazioni.
Una pagina di sommario sostituita diventa da quel momento una pagina normale. Le sottolineature e il testo dei collegamenti creati con KanzonasPDF vengono
ridisegnati sul nuovo disegno; un collegamento su parole che nel nuovo disegno non sono nella stessa
posizione (un richiamo di tavola che si è spostato) resta dov'era e viene segnalato, così puoi controllarlo.
Intestazioni, piè di pagina, filigrane, sfondi e modifiche al testo scritti nel vecchio disegno se ne vanno con
esso. I livelli dei nuovi disegni si uniscono ai livelli del documento (scheda Livelli), attivi o disattivi come nel nuovo
file. Le annotazioni delle pagine del nuovo file non vengono portate, e il nuovo file non viene modificato.
Ctrl+Z annulla l'intera sostituzione in un solo passaggio. Un documento protetto contro le modifiche non la
consente.</li>
<li>Menu Pagine: Inserisci pagina vuota dopo la corrente (delle stesse dimensioni della pagina corrente), Estrai
pagine in un nuovo file (in un nuovo file, non nel documento stesso), Elimina pagine (le pagine selezionate nell'elenco
delle pagine, o la pagina corrente; chiede conferma, e Ctrl+Z le ripristina). Un segnalibro a una
pagina eliminata porta poi alla pagina successiva (o all'ultima pagina).</li>
<li>Scheda <b>Livelli</b>: mostra o nascondi i livelli CAD / di contenuto opzionale. <b>Annotazioni sui
livelli</b> (come in Bluebeam): <b>Nuovo livello...</b> aggiunge un livello al documento, e <b>Le nuove
annotazioni vanno su</b> sceglie il livello su cui vanno le annotazioni che disegni (Nessun livello: nessuno).
Per mettere su un livello annotazioni già disegnate, selezionale e fai clic destro &gt; <b>Livello</b> &gt; un
livello, Nessun livello o Nuovo livello.... Un'annotazione su un livello nascosto non viene disegnata e non si
può cliccare; resta nel file. Le annotazioni con lo stile cambiato, spostate e copiate restano sul loro
livello. I livelli sono quelli del PDF stesso, quindi anche Acrobat e gli altri programmi con i livelli
mostrano e nascondono le annotazioni insieme a loro. L'Elenco annotazioni ha una colonna Livello e, quando il
documento ha dei livelli, un elenco per mostrare le annotazioni di un solo livello.</li>
<li>Scheda <b>Segnalibri</b>: aggiungi, rinomina, riordina e rientra i segnalibri, creali dai
titoli e inserisci un sommario (vedi Segnalibri e sommario).</li>
<li><b>Collega i richiami alle tavole</b> (menu Pagine; scheda Pagine, sotto la freccia del gruppo Documento): per una serie di disegni stampata senza
collegamenti ipertestuali. KanzonasPDF legge il numero e il titolo di ogni tavola dal suo cartiglio (il
valore dopo una didascalia SHEET, SHEET NO o DWG NO, o il numero più grande che somiglia a un numero di tavola nell'area
del cartiglio) e li mostra per la correzione. Poi ogni bolla di richiamo, nota o riga di indice
che cita una di quelle tavole (3/A-501, SEE A-201, A101 e A-101 contano come la stessa) diventa un
collegamento a quella pagina; un numero che non è una pagina qui ma è nel nome di un PDF nella stessa
cartella (A-501 Details.pdf) collega a quel file. Le parole che hanno già un collegamento restano invariate,
quindi i collegamenti ipertestuali propri di AutoCAD restano ed eseguirlo due volte non aggiunge nulla. Opzioni: un sottile riquadro blu
attorno ai collegamenti (disattivato per impostazione predefinita, per tenere puliti i disegni) e segnalibri con il numero
e il titolo della tavola. Ctrl+Z annulla tutto.</li>
</ul>

<h2 id="sets">Raccolte: più PDF come uno solo</h2>
<p>Come i Sets di Bluebeam: una serie di disegni tenuta come un PDF per tavola (o i disegni e il
capitolato di un progetto) sfogliata come un solo documento, senza combinare i file. Ogni PDF resta
com'è, e le annotazioni vengono salvate nel file su cui sono disegnate.</p>
<ul>
<li><b>Nuova raccolta...</b> (menu File; scheda Pagine, sotto la freccia del gruppo Crea; o il pulsante
Raccolta del pannello <b>Raccolte</b>): scegli i PDF, poi dove salvare la raccolta. Una raccolta è un
piccolo file a sé (.kzset) che elenca i PDF; quelli nella sua cartella o sotto vengono tenuti in base alla
loro posizione rispetto a esso, così la cartella si può spostare o condividere con la raccolta dentro.
<b>Apri raccolta...</b> ne apre una (come trascinare un file .kzset sulla finestra).</li>
<li>Il pannello <b>Raccolte</b> (una scheda del pannello di sinistra e un'icona sulla barra dei pannelli)
elenca ogni file con le sue pagine sotto. Nelle pagine di formato da disegno (11x17 e più grandi) il numero
e il titolo della tavola vengono letti dal cartiglio (SHEET NO, SHEET TITLE), così compare A-101 FLOOR PLAN;
le altre pagine con la loro etichetta o il loro numero. Un file che non si trova viene elencato in grigio.
Scrivi in <b>Filtra tavole</b> per trovare una tavola dal suo numero o titolo.</li>
<li>Fai clic su una tavola per aprire il suo file a quella pagina. <b>&#9654;</b> (Tavola successiva) e
<b>&#9664;</b> (Tavola precedente) vanno pagina per pagina attraverso i file: dopo l'ultima pagina di un file
viene la prima del successivo. Un file aperto dalla raccolta viene richiuso quando passi a un altro file, a
meno che tu non l'abbia modificato, così sfogliare una raccolta di 60 tavole non lascia 60 schede.</li>
<li>Fai clic destro su un file nel pannello per <b>Sposta su</b>, <b>Sposta giù</b> o <b>Rimuovi dalla
raccolta</b>; il pulsante Raccolta ha <b>Aggiungi file...</b>, <b>Rinomina raccolta...</b>, <b>Chiudi
raccolta</b> e <b>Combina in un solo PDF...</b> (Combina file con i file della raccolta, nel suo ordine).
Una modifica alla raccolta viene salvata subito nel suo file.</li>
</ul>

<h2 id="bookmarks">Segnalibri e sommario</h2>
<p>I segnalibri (la struttura del PDF) sono elencati nel pannello <b>Segnalibri</b> (F9). Fai clic su uno per andare
al suo punto. I pulsanti sopra l'elenco aggiungono un segnalibro alla pagina corrente (+), rinominano, eliminano,
spostano su e giù, e aumentano il rientro (lo rendono figlio di quello sopra) o lo riducono. Il pulsante <b>⋯</b>,
il clic con il pulsante destro nell'elenco e <b>Documento &gt; Strumenti segnalibri</b> offrono il resto. Ogni modifica è
un passaggio di annullamento (Ctrl+Z), e modificare un segnalibro mantiene punti, zoom e stili degli altri.</p>
<ul>
<li><b>Aggiungi segnalibro alla vista corrente</b> (Ctrl+B, quando non stai modificando testo): un segnalibro al
punto mostrato dalla finestra, dopo il segnalibro selezionato. Con del testo selezionato, il segnalibro porta
a quel testo e prende il suo nome.</li>
<li><b>Imposta la destinazione del segnalibro sulla vista corrente</b>: il segnalibro selezionato ora porta al
punto mostrato dalla finestra (nome e stile restano).</li>
<li><b>Ordina segnalibri per pagina</b> (in ordine di pagina, poi dall'alto in basso nella pagina) o
<b>Ordina segnalibri per nome</b> (i numeri in ordine numerico: A-2 prima di A-10). I figli di ogni
segnalibro si spostano con esso e vengono ordinati anch'essi.</li>
<li><b>Espandi tutti i segnalibri</b> e <b>Comprimi tutti i segnalibri</b> aprono o chiudono l'intero elenco
(solo nel pannello; il documento non cambia).</li>
<li><b>Segnalibro in grassetto (sì/no)</b>, <b>Segnalibro in corsivo (sì/no)</b> e <b>Colore
segnalibro...</b> applicano lo stile al segnalibro selezionato. Vengono salvati nel PDF, quindi li mostrano anche Acrobat e
gli altri lettori.</li>
</ul>
<p><b>Crea segnalibri dal documento.</b> Tre comandi trovano i segnalibri per te. Ognuno
legge le pagine con una barra di avanzamento (Annulla lo interrompe), poi mostra ciò che ha trovato come un albero da
controllare prima che cambi qualcosa: deseleziona ciò che non deve essere un segnalibro, fai doppio clic su un nome per
cambiarlo, seleziona i segnalibri e fai clic su <b>Livello su</b> o <b>Livello giù</b>, e scegli quanti
<b>Livelli</b> tenere (da 1 a 3). Se fai clic su un segnalibro lì, vedi il suo punto sulla pagina. Seleziona
<b>Nomi in maiuscolo con le iniziali maiuscole</b> per scrivere PIANTA PRIMO PIANO come Pianta Primo Piano. Quando il
documento ha già dei segnalibri, scegli se i nuovi li sostituiscono o vengono dopo di essi.
<b>Crea segnalibri</b> li crea tutti in un unico passaggio di annullamento.</p>
<ul>
<li><b>Crea segnalibri dai titoli...</b> trova i titoli dal loro aspetto: testo chiaramente
più grande del corpo del testo, righe in grassetto isolate, e titoli numerati (1.2 Scope,
SECTION 08 71 00, PART 2 - PRODUCTS, Chapter 3). I livelli sono gli stessi in tutto il
documento: il testo più grande è un livello superiore, poi il grassetto, poi la numerazione (SECTION sopra PART sopra
1.1 sopra 1.1.1); la finestra indica quale aspetto è diventato quale livello. Intestazioni, piè di pagina e numeri
di pagina ripetuti pagina dopo pagina vengono esclusi, così come le righe di una pagina di sommario.
Una singola riga più grande di tutto il resto all'inizio (il titolo del documento) viene elencata
deselezionata. È veloce anche sui documenti lunghi (un secondo o due per 500 pagine).</li>
<li><b>Segnalibri dalla struttura con tag...</b> è per i PDF con tag (la maggior parte dei PDF salvati da Word
e i PDF accessibili): i loro titoli sono marcati da H1 a H6, quindi i segnalibri sono esattamente i
titoli e i livelli del documento. Su un PDF senza tag lo segnala.</li>
<li><b>Segnalibri dai numeri di tavola...</b> è per le serie di disegni: un segnalibro per ogni tavola,
con il numero e il titolo della tavola (A-101  PIANTA PRIMO PIANO), letti dai cartigli come
li legge Collega i richiami alle tavole. Seleziona <b>Raggruppa le tavole per disciplina</b> per metterle sotto
G - Generale, A - Architettonico, S - Strutturale, M - Meccanico e così via (le lettere del National CAD
Standard statunitense).</li>
</ul>
<p><b>Inserisci sommario...</b> (menu Documento, menu Pagine, o il ⋯ del pannello Segnalibri)
aggiunge pagine che elencano i segnalibri: un titolo, ogni segnalibro con i puntini di riempimento e il suo numero di pagina,
i livelli rientrati e in caratteri più piccoli, e ogni riga un collegamento alla sua pagina. Il testo è scritto con
font incorporati nelle pagine, così il sommario appare uguale in ogni lettore e supera il controllo di Salva come
PDF/A, e ogni titolo è un unico blocco di testo che <b>Modifica testo</b> apre per intero (a capo come
prima). Scegli il titolo, quanti
livelli elencare, dove va (all'inizio del documento o prima della pagina corrente)
e la dimensione della pagina (quella della pagina prima di cui va, Letter o A4). I numeri di pagina sono quelli
delle pagine dopo l'inserimento delle nuove. Eseguilo di nuovo dopo aver cambiato i segnalibri e
scegli <b>Al posto del sommario creato prima</b>: le vecchie pagine vengono sostituite da quelle
nuove, invece di aggiungere un altro sommario. I segnalibri che portano a una pagina web o a un altro file non vengono
elencati, e i titoli sulle pagine del sommario non diventano mai segnalibri. Il collegamento di ogni riga
è descritto per i lettori di schermo ("Risultati, pagina 4") e i puntini di riempimento sono marcati come
decorazione; in un documento con tag il sommario riceve i tag di un sommario (una voce per
riga, ognuna un collegamento con le parole e il numero di pagina della riga). È un unico passaggio
di annullamento, e chiede di sbloccare l'ordine delle pagine quando l'elenco delle pagine è bloccato.</p>

<h2 id="scan">Scansione</h2>
<p><b>Scansiona...</b> (menu File, scheda Pagine &gt; gruppo Crea, o la tavolozza dei comandi) acquisisce pagine
da uno scanner, o da una stampante che scansiona, in un PDF. Comunica con la maggior parte delle stampanti di rete senza
installarne i driver, in uno di questi modi:</p>
<ul>
<li><b>eSCL (AirScan)</b>: la scansione senza driver delle stampanti Mopria e Apple AirPrint (la maggior parte
delle stampanti prodotte negli ultimi dieci anni). Viene trovata in rete automaticamente.</li>
<li><b>WSD</b> (Web Services on Devices): la scansione di rete di Microsoft, offerta da molte stampanti
(Dell, Brother, Canon, Epson, HP, Kyocera, Xerox...). Viene trovata automaticamente; su molte stampanti va
prima attivata nella pagina web della stampante (WSD impostato su Enable).</li>
<li><b>WIA</b> (Windows): gli scanner che Windows stesso conosce, compresi gli scanner USB e quelli
di cui è installato il driver del produttore.</li>
<li><b>SANE</b> (Linux): gli scanner che il comando scanimage conosce (installa il pacchetto sane-utils;
sane-airscan vi aggiunge gli scanner di rete senza driver).</li>
<li>Su macOS, per ora eSCL e WSD (gli scanner USB non sono ancora supportati lì). Alla prima
scansione viene chiesto di permettere a KanzonasPDF di trovare dispositivi sulla rete locale: scegli <b>Consenti</b> (per cambiarlo
in seguito: Impostazioni di Sistema &gt; Privacy e sicurezza &gt; Rete locale).</li>
</ul>
<p>Per scansionare:</p>
<ul>
<li>La finestra elenca gli scanner trovati, ognuno con il modo in cui viene raggiunto (eSCL, WSD, WIA o
SANE) e il suo indirizzo; una stampante trovata in più modi compare una volta per ciascuno. Scegline uno; l'ultimo
scanner usato è elencato e già scelto per te. <b>Aggiorna</b> cerca di nuovo.</li>
<li><b>Aggiungi per indirizzo...</b>: quando la stampante non viene trovata (le reti Wi-Fi ospiti, alcuni router e
le sottoreti diverse bloccano il rilevamento), digita il suo indirizzo IP, mostrato sul suo pannello o nel rapporto
di configurazione di rete (per esempio 192.168.1.20). KanzonasPDF prova prima eSCL, poi WSD.</li>
<li>Scegli l'<b>Origine</b> (Piano di scansione (vetro), Alimentatore documenti o Alimentatore documenti, fronte-retro,
quando lo scanner li ha), il <b>Colore</b> (Colore, Scala di grigi, Bianco e nero),
la <b>Risoluzione</b> (quelle offerte dallo scanner; 300 dpi va bene per documenti e OCR) e le <b>Dimensioni
pagina</b> (Letter, Legal, A4 o la più grande consentita dallo scanner). Vengono ricordate per la volta
successiva.</li>
<li>Fai clic su <b>Scansiona</b>. La finestra mostra l'avanzamento, e <b>Annulla</b> lo interrompe. Dall'alimentatore
documenti viene scansionata ogni pagina presente. Poi <b>Scansiona altre pagine</b> ne aggiunge altre (metti la
pagina successiva sul vetro, o la pila successiva nell'alimentatore), e <b>Fatto</b> le mette tutte in un
PDF.</li>
<li><b>Avvia la scansione dalla stampante</b> (stampanti WSD): mentre la finestra mostra una stampante WSD,
KanzonasPDF le chiede di elencare questo computer come destinazione di scansione ("KanzonasPDF - " e
il nome del computer). Sul pannello della stampante scegli Scansione, poi Scansione su computer (WSD), scegli quel
nome e premi Avvio: le pagine arrivano nella finestra, con le impostazioni della finestra (scegli prima lì
l'origine). Windows chiede una volta se consentire KanzonasPDF sulle reti private: consentilo,
altrimenti la stampante non può raggiungere la finestra. La stampante dimentica questo computer quando la finestra
si chiude.</li>
<li><b>Inserisci le pagine in</b>: <b>Un nuovo documento</b> (una scheda non salvata; Salva chiede dove salvarlo),
o <b>Questo documento, dopo la pagina corrente</b> (Ctrl+Z le toglie di nuovo tutte in un solo passaggio).
Seleziona <b>Rendi le pagine ricercabili</b> per eseguire Riconosci testo (OCR) sulle nuove pagine.</li>
<li><b>Monitora una cartella...</b> è per una stampante che sa scansionare solo in una cartella di rete (Scansione su
cartella di rete, SMB) o via FTP: scegli la cartella in cui scansiona; ogni nuovo PDF o immagine (JPEG,
PNG, TIFF) che vi arriva mentre la finestra è aperta viene aggiunto come pagine scansionate, quando ha
smesso di crescere e sembra completo (un file che resta incompleto per un minuto viene segnalato come
incompleto). I collegamenti a file che si trovano altrove vengono ignorati. Un PDF (dalla cartella o dallo scanner)
porta solo il disegno e il testo delle sue pagine, senza collegamenti, campi modulo o commenti. Fai clic su Fatto
quando sono arrivati tutti.</li>
</ul>
<p>Quando non funziona, la finestra spiega il motivo con parole semplici, e cosa provare:</p>
<ul>
<li><b>Nessuno scanner trovato</b>: il computer e la stampante devono essere sulla stessa rete (non una
rete Wi-Fi ospiti); prova Aggiungi per indirizzo con l'indirizzo IP della stampante. Se Windows chiede se consentire a
KanzonasPDF di usare le reti private, consentilo: è così che le risposte delle stampanti tornano indietro.</li>
<li><b>La scansione WSD è disattivata</b>: apri la pagina web della stampante (digita http:// e il suo indirizzo
IP in un browser), trova WSD (spesso in Rete, Protocolli o Servizi), impostalo su
Enable, salva, poi fai clic su Aggiorna.</li>
<li><b>Lo scanner non accetta scansioni dal computer</b>: alcune stampanti scansionano solo quando la
scansione viene avviata dal loro pannello: tieni aperta la finestra Scansiona con la stampante scelta, poi sulla
stampante scegli Scansione su computer (WSD) e il nome di questo computer.</li>
<li><b>Una Dell E525w, o una stampante simile</b>: attiva WSD nella sua pagina web (vedi sopra), poi prova
entrambi i modi: fai clic su Scansiona in KanzonasPDF (avvio dal computer); se la stampante non la
accetta, avvia la scansione dal pannello della stampante con Scansione su computer (WSD) e il nome di questo computer
(avvio dalla stampante). Se nessuno dei due funziona, usa Copia dettagli.</li>
<li><b>Copia dettagli</b> copia ciò che è stato trovato e le risposte dello scanner stesso (niente di personale;
i numeri di serie vengono esclusi). Se lo scanner continua a non funzionare, incollali in una segnalazione sulla
pagina GitHub di KanzonasPDF, così potrà essere supportato.</li>
<li>Sicurezza: KanzonasPDF comunica solo con lo scanner che scegli (o con l'indirizzo che digiti), legge le sue
risposte con limiti rigidi di dimensione e di tempo, e non invia nulla altrove. Gli scanner di rete
usano propri certificati autofirmati per HTTPS; ognuno viene accettato solo per il suo scanner. Un
file scansionato (per esempio un TIFF multipagina) può avere al massimo 6.000 megapixel in totale, ben oltre 100
pagine Letter a colori a 600 dpi: scansiona meno pagine alla volta, o a una risoluzione più bassa.</li>
</ul>

<h2 id="printprod">Produzione di stampa (scheda Stampa)</h2>
<p>Ciò che serve a una tavola prima di andare a un plotter o in tipografia. La scheda <b>Stampa</b> ha questi
comandi accanto a Stampa e Ritaglia; si trovano anche in <b>Pagine &gt; Produzione di stampa</b>.</p>
<ul>
<li><b>Imposta riquadri di pagina</b>: oltre al riquadro di ritaglio (ciò che viene mostrato), una pagina PDF può avere un
<b>riquadro di rifilo</b> (il formato finito, dove si taglia il foglio), un <b>riquadro di abbondanza</b> (quanto il
disegno prosegue oltre il rifilo, così dopo il taglio non resta un bordo bianco) e un <b>riquadro grafico</b> (il
contenuto significativo). Per ciascuno scegli Lascia invariato, Imposta o Rimuovi; un riquadro si imposta con i suoi margini
verso l'interno rispetto alla pagina come viene mostrata (i margini positivi vanno verso l'interno), in punti, pollici o millimetri, su tutte
le pagine, sulla pagina corrente o su un elenco di pagine. Un riquadro deve restare entro l'intero foglio della pagina
(il suo riquadro supporto), e il riquadro di abbondanza deve contenere il riquadro di rifilo: altrimenti viene segnalato e
non cambia nulla. Ctrl+Z annulla l'operazione.</li>
<li><b>Mostra riquadri di pagina</b> (anche nel menu Visualizza) traccia il contorno dei riquadri che ha una pagina: il rifilo in
verde, l'abbondanza in rosso, l'area grafica in blu, ciascuno con il suo nome in un angolo (Rifilo, Abbondanza, Area grafica; solo
sullo schermo).</li>
<li><b>Correggi linee sottili</b>: le linee disegnate più sottili di uno spessore che scegli (0,25 pt per impostazione predefinita;
compreso lo spessore 0, che significa "il più sottile che il dispositivo può disegnare", spesso troppo tenue su
un plotter) vengono disegnate con lo spessore scelto, su tutte le pagine, sulla pagina corrente o su un elenco di
pagine. Agisce sul disegno della pagina stessa e sui gruppi di disegno che la pagina inserisce (anche un gruppo inserito da altre
pagine ha lì le linee ingrossate); per il resto ogni linea rimane
uguale. Le annotazioni mantengono il loro spessore. Ctrl+Z annulla l'operazione.</li>
<li><b>Verifica per la stampa</b> elenca ciò che spesso va storto in tipografia, per tipo, ciascuna voce con
la sua pagina (fai doppio clic su una riga per andarci): font non incorporati (la stampante ne mette
un altro), immagini con meno di 150 pixel per pollice alla dimensione di stampa, immagini in colori RGB
(una macchina da stampa in quadricromia le converte), formati di foglio misti, pagine senza riquadro di rifilo o
senza abbondanza oltre il rifilo, e linee più sottili di 0,25 pt (con un pulsante per Correggi linee sottili). È
una verifica rapida dei problemi comuni, non un controllo preliminare secondo uno standard di stampa come PDF/X.</li>
<li><b>Segni di taglio</b> (nella finestra Stampa): segni agli angoli del riquadro di rifilo di ogni pagina,
all'esterno, con il disegno stampato fino al riquadro di abbondanza; una pagina senza riquadro di rifilo riceve i segni
ai suoi bordi. Sono solo sulla carta: il file non cambia. Il riquadro di rifilo, con lo spazio per
i segni, viene adattato alla carta (Adatta alla carta o Dimensioni reali, come impostato lì).</li>
</ul>

<h2 id="forms">Moduli</h2>
<ul>
<li><b>Compilare:</b> con Seleziona o Mano, fai clic su un campo. I pulsanti di opzione con lo stesso nome di
gruppo si escludono a vicenda: sceglierne uno deseleziona gli altri del gruppo. La lunghezza massima di un campo
viene rispettata; un elenco a discesa che lo consente accetta anche un valore digitato (Digita un valore...). KanzonasPDF
non esegue mai il JavaScript di un modulo: riconosce i calcoli, i formati e i controlli standard
che scrive Acrobat e li esegue da sé (vedi sotto); qualsiasi altro script resta nel file ma
non viene eseguito, quindi ciò che calcolerebbe non si aggiorna (controllalo, oppure compila quel modulo in Acrobat
Reader).</li>
<li><b>Campo modulo successivo</b> (Tab) e <b>Campo modulo precedente</b> (Shift+Tab), nel menu Moduli:
scorrono i campi nell'ordine di tabulazione della pagina (se non è stato cambiato con Imposta ordine di tabulazione...:
pagina dopo pagina, dall'alto in basso, da sinistra a destra come viene mostrata la pagina, anche su una pagina ruotata). Il
campo corrente riceve un contorno arancione; un campo di testo si apre per la digitazione (Tab va avanti, Shift+Tab
torna indietro); per una casella di controllo, un pulsante di opzione, un elenco a discesa, un campo firma o un campo sigla premi
<b>Spazio</b> o <b>Invio</b> per compilarlo. Esc toglie il contorno.</li>
<li><b>Evidenzia campi modulo</b> (menu Visualizza o Moduli, attivo per impostazione predefinita) ombreggia di blu ogni campo compilabile
con un contorno blu; i campi obbligatori ricevono un contorno rosso. L'ombreggiatura è solo sullo schermo.</li>
<li><b>Creare:</b> menu Moduli: campo di testo, casella di controllo, pulsante di opzione, elenco a discesa, campo firma,
campo sigla. Un <b>campo sigla</b> funziona come un campo firma: chi compila il
modulo ci fa clic per apporvi la propria sigla salvata. Fai doppio clic su un campo (con uno strumento modulo), oppure
fai clic su di esso con il tasto destro, per aprire le sue Proprietà campo. Nella scheda Moduli della barra multifunzione, il gruppo <b>Moduli intelligenti</b>
contiene Rileva campi, Proprietà campo, Ordine di tabulazione e Verifica obbligatori (i comandi descritti sotto).</li>
<li><b>Rileva campi modulo...</b> (menu Moduli, o clic con il tasto destro sulla pagina con uno strumento modulo) trova
dove vanno i campi in un modulo piatto: un PDF senza campi, o uno scansionato dopo Riconosci testo
(OCR). Cerca righe vuote dopo un'etichetta ("Nome: ____", disegnate o scritte con trattini bassi) o
con l'etichetta sotto, riquadri vuoti e celle di tabella accanto a un'etichetta o sotto un'intestazione di colonna
(Q.tà 1, Q.tà 2, ...), riquadri con una piccola etichetta all'interno, e piccoli quadrati con un'etichetta
accanto (caselle di controllo); un'etichetta "Firma" o "Sigla" crea un campo firma o un campo sigla
e un'etichetta "Data" un campo data. Ogni campo prende il nome dalla sua etichetta. Prima di qualsiasi modifica,
un elenco mostra ciò che è stato trovato (ogni elemento è indicato anche sulla pagina con un riquadro tratteggiato arancione): togli la spunta a ciò
che non vuoi (Seleziona tutto / Deseleziona tutto), cambia un nome o un tipo, poi <b>Crea campi</b>
li crea in un solo passaggio (Ctrl+Z annulla l'operazione). È prudente più che zelante: una riga o un riquadro senza
etichetta vicina, il testo sottolineato, i filetti tra i paragrafi e il bordo della pagina vengono lasciati
stare, quindi aggiungi con gli strumenti descritti sopra i campi che non ha trovato.</li>
<li><b>Proprietà campo...</b> (menu Moduli, o clic con il tasto destro su un campo; prima seleziona il campo
con uno strumento modulo, o raggiungilo con Tab). <i>Generale:</i> nome, descrizione comando (mostrata quando il puntatore si ferma sul
campo), Obbligatorio, Sola lettura, le opzioni di un elenco a discesa e la sua Posizione nell'ordine di tabulazione.
<i>Formato</i> (campi di testo): Numero (cifre decimali, stile dei separatori come 1,234.56 o
1.234,56, un simbolo di valuta prima o dopo il numero, numeri negativi con il segno meno o tra
parentesi), Percentuale (un numero digitato è una percentuale: 25 o 25% viene mostrato come 25.00%, e 0.5 come
0.50%; il valore viene conservato come frazione, 0.25, così i calcoli percentuali di Acrobat funzionano ancora;
Acrobat stesso mostrerebbe un 25 senza simbolo come 2500.00%), Data (un
formato come dd/mm/yyyy: d giorno, m mese, mmm Jan, mmmm January (i mesi in inglese, come in Acrobat), yy o yyyy anno), o Speciale
(codice postale ZIP, codice ZIP+4, numero di telefono, numero di previdenza sociale SSN). Il valore viene conservato senza formato (1234.5)
e mostrato formattato ($1,234.50). <i>Convalida:</i> un intervallo in cui deve rientrare il valore (Da / A;
per un campo percentuale, della frazione conservata: da 0 a 1 per 0% a 100%, come in Acrobat).
<i>Calcolo:</i> il valore del campo è la Somma, il Prodotto, la Media, il Minimo o il Massimo dei
campi che spunti, oppure una Formula come <b>Prezzo * Qta + Spedizione</b> (nomi di campo, numeri,
+ - * / e parentesi; un nome con spazi richiede una barra rovesciata prima di ogni spazio: Articolo\\ 1;
fino a 50 parentesi o segni annidati l'uno nell'altro e 250 termini di seguito; una formula più lunga in un
modulo creato altrove viene mostrata come Calcolo personalizzato (non eseguito)).
Ogni modifica è un singolo passaggio di annullamento.</li>
<li><b>Campi calcolati</b>: vengono calcolati appena viene compilato un campo che usano (Invio,
Tab o un clic altrove), ciascuno dopo i campi che usa, così un subtotale alimenta un totale; un campo
vuoto conta come 0 e una divisione per zero lascia vuoto il risultato. Quando un campo (o la
pagina in cui si trova) viene eliminato, i campi che lo usavano vengono ricalcolati senza di esso. In un campo calcolato non
si digita. KanzonasPDF li calcola con un proprio piccolo lettore di formule e li salva come fa
Acrobat (con il suo AFSimple_Calculate standard e la notazione di campo semplificata, con l'ordine di
calcolo del modulo), così anche Acrobat e gli altri lettori li calcolano; un modulo creato in Acrobat
con questi calcoli viene calcolato qui allo stesso modo. Qualsiasi altro script di calcolo viene mostrato
in Proprietà campo come Calcolo personalizzato (non eseguito).</li>
<li><b>Controllo di ciò che digiti:</b> un campo numero, percentuale, telefono, ZIP o previdenza sociale accetta
solo i caratteri adatti mentre digiti. Un valore che non rispetta il formato del campo (una
data che non esiste, un numero di telefono con troppe poche cifre) o il suo intervallo viene rifiutato: un messaggio
spiega perché, il campo mantiene il valore precedente e si riapre con ciò che hai digitato, per correggerlo.
Formati e controlli vengono salvati come quelli standard di Acrobat (AFNumber_Format, AFDate_FormatEx,
AFRange_Validate e simili), così anche gli altri lettori li applicano.</li>
<li><b>Campi obbligatori:</b> con Salva e Stampa, i campi obbligatori ancora vuoti vengono
segnalati in rosso ed elencati in un avviso nella parte superiore del documento (Vai al primo ti porta
lì); il file viene comunque salvato o stampato. <b>Verifica campi obbligatori</b> (menu Moduli)
fa lo stesso in qualsiasi momento; compilare un campo segnalato ne toglie la segnalazione.</li>
<li><b>Imposta ordine di tabulazione...</b> (menu Moduli, o clic con il tasto destro con uno strumento modulo): l'ordine in cui Tab scorre
i campi di una pagina: Per righe, Per colonne (per questa pagina o per tutte), oppure Manuale: trascina i
campi nell'elenco, o usa Sposta su e Sposta giù. Viene salvato nella pagina, così anche gli altri lettori
lo seguono; Posizione nell'ordine di tabulazione, in Proprietà campo, sposta un solo campo.</li>
</ul>

<h2 id="sign">Proteggi: firme, password, oscuramento</h2>
<p>Tutto ciò che è descritto qui si trova nel menu <b>Proteggi</b>.</p>
<ul>
<li><b>Firma autografa / sigla:</b> Firma (G) o Sigla (I), poi fai clic per posizionare la tua firma
o la tua sigla. La prima volta ti viene chiesto di configurarla (disegnala o carica una sua immagine, con un PIN
facoltativo); per sostituirla in seguito, usa File &gt; Preferenze &gt; Utente &gt; Configura la mia firma... / Configura la mia
sigla.... Per scegliere la dimensione, <b>trascina un riquadro</b> invece di fare clic: viene posizionata larga quanto
il trascinamento (l'altezza segue le sue proporzioni). La dimensione usata con un clic si imposta in File &gt;
Preferenze &gt; Utente (all'inizio 2 pollici per una firma e 0,75 pollici per la sigla). Dopo, torna attivo
lo strumento della modalità mouse (Mano, Seleziona, o Modifica oggetti in modalità CAD), così non ne
posizioni una seconda per sbaglio. Come qualsiasi immagine della pagina, una firma posizionata si può spostare o eliminare con Modifica
oggetti (oppure con Ctrl+Z subito dopo averla posizionata).</li>
<li><b>Data</b> (Ctrl+;, scheda e menu Proteggi): fai clic per scrivere lì la data di oggi, per esempio
accanto a una firma o nel campo data del documento stesso. Inserire la data in un campo modulo (e firmare un
campo firma o un campo sigla) funziona in un modulo protetto che consente la compilazione dei campi modulo e la
firma. È separata dalla firma, così un modulo
che stampa già una data non ne riceve due. Il formato (come 08/10/2026 o 08 ottobre 2026)
si imposta in File &gt; Preferenze &gt; Utente.</li>
<li><b>Firma o sigla in più punti:</b> metti la tua sigla (o la tua firma) su tutte le pagine,
su tutte tranne la prima o l'ultima, o sulle pagine che indichi, nello stesso punto dell'ultima che hai posizionato
o in un angolo.</li>
<li><b>Aggiungi segnaposto firma:</b> trascina dei riquadri dove devono andare le firme o le sigle
(scegli quale in Proprietà). <b>Applica tutti i segnaposto firma</b> poi li compila tutti
con la firma o la sigla salvata e la data.</li>
<li><b>Firma digitalmente con certificato</b>, con un blocco facoltativo contro le modifiche (certificazione).
Scegli da dove proviene il certificato:
<ul>
<li><b>Certificato archiviato in Windows</b> (solo su Windows; non compare su Linux né su macOS): l'elenco mostra i certificati di firma del tuo
archivio Personale di Windows, gli stessi che usano Adobe Acrobat e PDF-XChange Editor (apri
certmgr.msc &gt; Personale &gt; Certificati per vederli). La firma la esegue Windows, quindi
funzionano anche i certificati la cui chiave non può essere copiata, le smart card e i token USB; Windows chiede
il PIN quando la chiave lo richiede. Per aggiungere lì un file .pfx/.p12, fai doppio clic su di esso. KanzonasPDF
ricorda il certificato che hai usato l'ultima volta.</li>
<li><b>Il mio certificato personale</b>: un certificato che KanzonasPDF crea per te la prima volta. Firma solo
documenti. Non è un'autorità di certificazione e non può emettere altri certificati.</li>
<li><b>File di certificato</b>: un file .pfx/.p12 di un'autorità di certificazione o della tua azienda,
con la sua password.</li>
</ul> I file firmati si aprono in sola lettura, così
la firma resta valida (un file i cui campi firma sono tutti vuoti non è firmato e si apre
normalmente). <b>Dettagli firma digitale</b> mostra chi ha firmato e se la firma è
ancora valida. <b>Cancella tutte le firme digitali</b> le rimuove (i campi vuoti restano).</li>
<li><b>Aggiungi marca temporale al documento:</b> ottiene una marca temporale attendibile da un server orario gratuito su Internet,
che prova che il file esisteva, senza modifiche, in quel momento. Viene salvato come nuova copia.</li>
<li><b>Oscuramento:</b> lo strumento Oscura (Shift+R) o Cerca e oscura segnano le aree. I segni di oscuramento
si possono selezionare, spostare e ridimensionare; <b>Applica gli oscuramenti selezionati</b> applica solo quelli
selezionati, Applica oscuramenti li applica tutti. L'applicazione rimuove, non si limita a coprire: il testo, le immagini
e i tratti vettoriali sotto un segno, e qualsiasi <b>campo modulo o annotazione</b> che un segno sovrappone (contengono una
propria copia del testo). Un campo rimosso non lascia nulla di sé nel file, e un campo calcolato
che lo usava viene ricalcolato senza di esso (contato come vuoto), così un totale non
rivela un prezzo oscurato; un campo calcolato oscurato non viene ricalcolato dai campi
rimasti. Un tracciato vettoriale che tocca un segno viene rimosso anche oltre il riquadro, compresa
la parte esterna. Una pagina oscurata perde anche la sua miniatura e la copia privata della pagina
che alcuni programmi (Illustrator) conservano nel file, e un intervallo con tag (le parole conservate di nuovo come
ActualText, per la lettura e la copia) coperto da un segno anche solo in parte perde quella copia delle sue
parole. L'applicazione elimina metadati, allegati, testo
nascosto, script e i dati privati di quei programmi, a meno che
tu non lo disattivi nella conferma (la casella è spuntata all'inizio). <b>Cerca e oscura</b> segna il testo
nelle pagine anche dove si trova in un livello nascosto o dove la pagina è ritagliata, e lo trova
dove un riquadro non può arrivare: campi
modulo (valori, opzioni degli elenchi, descrizioni comando e nomi, anche di campi che non stanno in nessuna pagina), collegamenti (indirizzi web e
di posta elettronica), note delle annotazioni (anche il loro testo formattato), titoli e indirizzi web dei segnalibri,
proprietà del documento (anche quelle proprie di un programma), il testo alternativo dei PDF con tag, le note dei collegamenti,
le etichette di pagina, i nomi dei livelli, i nomi delle destinazioni e il titolo memorizzato da un sommario. Quando applichi, i campi, i collegamenti, i timbri e
gli allegati che lo contengono vengono eliminati (e un modulo XFA che lo contiene: i suoi campi normali restano), mentre nelle note e nei commenti (che restano), nei segnalibri
e nelle proprietà (e in quegli altri punti) viene sostituito da [redacted]. Se il testo si trova solo in quei punti, Cerca e oscura indica dove l'ha trovato (i
campi, le note, i collegamenti, i segnalibri e le proprietà, e in quanti altri punti del file, come
nomi dei livelli, indirizzi web, dati dei moduli e testo alternativo) e propone di rimuoverlo
subito. Una <b>legenda</b> viene ridisegnata dalle annotazioni rimaste, nello stesso passaggio: le sue righe non
mostrano più ciò che è stato oscurato, e il testo del suo titolo viene sostituito da [redacted] (un riquadro disegnato sopra una
legenda la rimuove). Controlla il risultato prima di condividerlo; Annulla funziona finché non chiudi il file.</li>
<li><b>Sanifica documento:</b> rimuove i dati nascosti che scegli: informazioni del documento (con i
dati privati che alcuni programmi, come Illustrator, conservano nel file), script,
allegati, testo nascosto, collegamenti, commenti, <b>commenti e annotazioni fuori dalla pagina</b> (conservati nello
spazio di lavoro: solo KanzonasPDF li mostra, quindi sono già selezionati per la rimozione), dati dei moduli (con un
modulo XFA, che conserva di nuovo i
dati; i suoi campi normali restano), miniature. Gli script comprendono anche quelli di
altre azioni (multimediali), i collegamenti javascript: e gli script di un modulo XFA (i campi normali del modulo
restano).</li>
<li><b>Proprietà di sicurezza (password &amp; permessi):</b> crittografia AES-256. Se fai clic su OK
senza alcuna casella spuntata su un documento protetto, ti viene chiesta conferma prima di rimuoverne la protezione.
  <ul>
  <li><i>Password di apertura:</i> nessuno può leggere il file senza di essa. È una protezione reale; se
  la dimentichi, il file non si può recuperare.</li>
  <li><i>Password dei permessi:</i> scegli cosa possono fare gli altri (stampare, copiare, commentare, compilare moduli,
  modificare il contenuto, modificare le pagine). Acrobat, PDF-XChange, Bluebeam e questa app la rispettano, ma
  alcuni strumenti gratuiti la ignorano, quindi non affidarti a essa per proteggere dati segreti.</li>
  <li><i>Moduli compilati:</i> quando <b>Compilazione dei campi modulo e firma</b> non è consentita, anche i
  campi del modulo diventano subito di sola lettura (Ctrl+Z annulla l'operazione), cosa che ogni lettore PDF
  rispetta, browser web compresi, così le risposte non si possono cambiare. Su un modulo già compilato,
  o quando proteggi un documento che hai appena firmato, questa casella è inizialmente senza spunta; spuntala per
  distribuire un modulo che altri devono compilare. Consentire di nuovo la compilazione dei moduli, o Rimuovi sicurezza, sblocca
  i campi bloccati in questo modo (i campi che erano già di sola lettura restano tali). Nemmeno KanzonasPDF
  compila i campi di sola lettura.</li>
  <li><i>Criteri:</i> salva le tue impostazioni abituali come criterio con un nome (le password non vengono mai salvate).</li>
  </ul>
  Le modifiche diventano effettive al salvataggio. Per ora non si possono aggiungere firme digitali e marche temporali a un
  PDF protetto da password: rimuovi la sicurezza, firma la versione definitiva e non aggiungere una
  password in seguito (renderebbe non valida la firma). <b>Rimuovi sicurezza</b> toglie la protezione (serve la
  password dei permessi). <b>Sblocca con password</b> ti permette di modificare un file con restrizioni e
  accetta la password dei permessi di un file che già consente la modifica, così puoi cambiarne
  la protezione; Proprietà di sicurezza e Rimuovi sicurezza chiedono prima quella password quando il
  file ne ha una. Un file protetto contro le modifiche si apre senza messaggi (il titolo della finestra
  riporta [protetto] e la barra di stato spiega il motivo); se provi a modificarlo, ti viene spiegato e indicato Sblocca
  con password.</li>
<li><b>Il salvataggio mantiene la protezione:</b> un file protetto da password resta protetto quando salvi
le modifiche, esattamente com'era: stessa crittografia, stessa password di apertura, stessa password dei permessi e
stesse restrizioni, anche se non conosci la password dei permessi. (Solo nel raro caso in cui la
protezione non possa essere mantenuta, KanzonasPDF chiede le password originali.) Usa Proprietà
di sicurezza (la nuova protezione usa AES-256) o Rimuovi sicurezza per cambiare la protezione
di proposito.</li>
<li><b>Il salvataggio mantiene le firme:</b> un file con firma digitale che non hai modificato viene salvato come
copia esatta (Salva o Salva con nome), così le sue firme restano valide. Solo dopo "Modifica comunque" il salvataggio
lo modifica, e allora la firma non risulta più valida.</li>
</ul>

<h2 id="document">Strumenti per i documenti</h2>
<ul>
<li><b>Riconosci testo (OCR):</b> rende le pagine scansionate ricercabili e selezionabili. Scegli le
<b>pagine</b> (Tutte, la pagina corrente o un elenco come 1-3, 7), se <b>saltare le pagine che
contengono già testo</b> (attivo per impostazione predefinita, così il testo non viene duplicato) e la <b>precisione</b>:
<b>Veloce</b> (150 dpi) per scansioni pulite con testo di dimensioni normali; <b>Normale</b> (300 dpi);
<b>Alta</b> (400 dpi, e verifica ogni orientamento, per caratteri piccoli, scansioni scadenti e
pagine di lato o capovolte; la più lenta); oppure <b>Automatica</b> (l'impostazione predefinita), che legge ogni
pagina in modo veloce e la rielabora ad alta risoluzione solo quando il testo risulta piccolo o poco chiaro.
Una precisione maggiore richiede più tempo, e non rende mai una scansione più nitida di
com'è stata acquisita (aggiungerebbe solo sfocatura), quindi su una scansione a 200 dpi Normale e Alta leggono a 200 dpi.
La tua scelta viene ricordata. Una pagina viene letta una porzione alla volta, e ciascuna viene disegnata solo quando viene
letta, quindi anche una tavola di 42 x 30 pollici in Alta richiede circa la stessa memoria di una pagina Letter; la
memoria usata dall'OCR torna al sistema al termine, e quella del motore OCR stesso (circa 45 MB)
due minuti dopo l'ultima pagina letta. Con qualsiasi precisione, una pagina scansionata capovolta viene riconosciuta e letta
raddrizzata, e le righe capovolte o in verticale sulla pagina ricevono il loro testo
dove si trovano le lettere, così Trova e Cerca e oscura coprono le parole giuste. Modifica testo poi
cambia le parole della scansione con un font corrispondente (vedi Modificare il testo del PDF).</li>
<li><b>Oscuramento:</b> lo strumento Oscura (segna testo o area) (Shift+R) o Cerca e oscura
segnano le aree; Applica oscuramenti rimuove in modo permanente ciò che c'è sotto. Un tracciato vettoriale che
tocca un segno viene rimosso anche oltre il riquadro. L'applicazione elimina metadati, allegati, testo nascosto
e script, a meno che tu non lo disattivi. Controlla il risultato prima di condividerlo.</li>
<li><b>Intestazione &amp; piè di pagina, numeri di pagina, Bates</b>, <b>Filigrana</b>,
<b>Comprimi (salva una copia più piccola)</b>, <b>Confronta documenti</b>, <b>Appiattisci</b> (rende le annotazioni parte della pagina).
La copia più piccola mantiene la protezione con password del documento (password di apertura, permessi), oppure la
protezione impostata in Proprietà di sicurezza e non ancora salvata.</li>
<li><b>Salva come PDF/A</b> (File &gt; <b>Salva come PDF/A...</b>): salva una copia d'archivio conforme a
PDF/A-2b (ISO 19005-2, livello B), lo standard per mantenere un documento leggibile e con lo stesso
aspetto per decenni, spesso richiesto da tribunali, uffici pubblici e archivi. Nella copia:
ogni font è incorporato (un font standard non incorporato, come Helvetica, Times, Courier, Symbol
e ZapfDingbats, o Arial, Times New Roman e Courier New, che vengono mostrati con questi, viene
incorporato dalle copie di KanzonasPDF, gli stessi font con cui li mostra, così il testo appare
e misura esattamente come prima); i colori sono definiti da un profilo colore (un intento di output
sRGB, e un profilo CMYK per i colori CMYK); i metadati dichiarano che è PDF/A, con titolo,
autore, oggetto e parole chiave uguali nelle proprietà del documento e nei metadati XMP; non c'è
JavaScript né alcuna azione che avvia un programma, riproduce contenuti multimediali o si esegue da sola (i collegamenti
a pagine e indirizzi web restano); ogni commento e annotazione ha un proprio aspetto ed è impostato
per la stampa, e quelli nascosti vengono rimossi (PDF/A mostra ogni annotazione, quindi una nascosta
apparirebbe); i campi modulo vengono disegnati (invece di lasciarlo al visualizzatore) e perdono le loro azioni; le impostazioni
dei livelli ricevono un nome; funzioni di trasferimento, metodi di fusione sconosciuti, smussatura delle immagini ingrandite,
compressione LZW (anche delle immagini scritte nel contenuto di una pagina) e versioni PDF successive alla 1.7 vengono sostituiti da ciò che PDF/A consente, senza cambiare
l'aspetto delle pagine. Gli <b>allegati</b> restano: quando sono tutti a loro volta file PDF/A, la
copia è PDF/A-2b; altrimenti è PDF/A-3b, la parte dello standard che consente qualsiasi file
allegato (ciascuno viene allora elencato come file associato al documento, con il suo tipo).
Le <b>firme digitali</b> vengono rimosse (i campi restano, vuoti): la copia è un nuovo file, nel quale
non potrebbero essere valide; firma la copia se serve una firma. Un documento <b>protetto da password</b>
non può essere salvato come PDF/A (un archivio deve aprirsi senza password): rimuovi prima la sua
sicurezza (Proteggi &gt; Rimuovi sicurezza). Il nome proposto è quello del documento con l'aggiunta di _PDFA.
Come dopo Salva con nome, la scheda mostra poi la copia (le modifiche non salvate sono lì; il file
originale resta com'era), e una finestra indica cosa è stato cambiato ed elenca ciò che non è stato possibile correggere,
ciascuno con la sua pagina.</li>
<li><b>Verifica PDF/A</b> (File &gt; <b>Verifica PDF/A...</b>) elenca ciò che impedisce al documento, così com'è
ora, di essere PDF/A, per tipo, ciascuna voce con la sua pagina (fai doppio clic su una riga per andarci) e
se Salva come PDF/A la corregge; un pulsante lì lo salva come PDF/A. Ciò che non si può correggere: un font
non incorporato che non è uno dei font standard (ricrea il PDF con i font
incorporati), un font standard le cui larghezze dei caratteri nel file differiscono da quelle del font
standard, una pagina più grande di 200 pollici o più piccola di 3 punti, PostScript, parti conservate in
altri file, una compressione insolita, un testo più lungo di 32.767 byte (un commento molto lungo) o
istruzioni di disegno annidate per più di 28 livelli. Verifica i requisiti comuni di PDF/A-2b (e di
PDF/A-3b per un file che dichiara di esserlo), non tutti: per una convalida formale, usa
<b>veraPDF</b>, gratuito, della PDF Association (verapdf.org).</li>
<li><b>Confronta documenti...</b> (menu Documento, scheda Pagine): scegli la revisione precedente (se è
protetta da password, KanzonasPDF ne chiede la password), poi come confrontare. <b>Testo, parola per parola</b> è per tutto ciò che va a capo in modo variabile (lettere,
capitolati, permessi, relazioni): le parole dei due documenti vengono confrontate nell'ordine di
lettura, così il testo che si è solo spostato di una riga o di una pagina non è una modifica. Il risultato è una copia
di questo documento con le parole aggiunte evidenziate in blu, un segno rosso dove sono state rimosse parole del
precedente (il commento del segno dice quali parole) e un riquadro attorno a ogni
immagine aggiunta, rimossa o ridimensionata. Ogni modifica è un'annotazione il cui commento
dice cosa è cambiato ("Prima: July 13  |  Ora: draft"), elencata nell'Elenco annotazioni, e una pagina di riepilogo
alla fine le elenca tutte; una modifica ripetuta su ogni pagina (un'intestazione) compare una sola volta con le sue
pagine. Un paragrafo spostato conta come rimosso in un punto e aggiunto nell'altro; una pagina scansionata
senza livello di testo viene confrontata solo come immagine (esegui prima l'OCR su entrambi i documenti per
confrontarne le parole). <b>Disegni, sovrapposti</b> è per piante e tavole: un nuovo
documento sovrappone i due in ogni pagina: rosso = solo nel precedente, blu = solo in questo,
grigio = invariato, con ogni area modificata racchiusa in una nuvola ed elencata nell'Elenco annotazioni. Se il
disegno si è spostato sul foglio tra una revisione e l'altra (ristampato con un margine diverso, per esempio), le
pagine vengono prima allineate, così compaiono solo le modifiche reali; la parte superiore della pagina indica di quanto si è
spostato. Una revisione stampata su un altro formato di carta (una tavola 24x36 e la sua stampa 11x17) viene scalata
alla dimensione della precedente, con una certa tolleranza per le linee più spesse di una stampa ridotta,
e la parte superiore della pagina lo indica. Due stampe dello stesso disegno non dovrebbero quindi mostrare
modifiche; se un risultato ha modifiche ovunque, i due file non sono lo stesso disegno alla
stessa scala. Il metodo adatto viene scelto per te (testo quando entrambi i documenti hanno un livello di testo
nella maggior parte delle pagine); puoi scegliere l'uno o l'altro.</li>
<li><b>Rimuovi filigrane...</b> (menu Documento): toglie le filigrane dalla pagina corrente, da tutte
le pagine o da pagine come 1-3, 7. Trova le filigrane aggiunte con Documento &gt; Filigrana e quelle
aggiunte da app che le contrassegnano come filigrane (Adobe Acrobat, PDF-XChange e altre), e le
annotazioni filigrana. Ctrl+Z annulla l'operazione. Una "filigrana" che è solo testo normale o un'immagine
nella pagina non si può distinguere dal resto della pagina; rimuovila con Cancella contenuto o
Modifica oggetti.</li>
<li><b>Sfondo...</b> (menu Documento; scheda Pagine, sulla freccia accanto a Intestazione e piè di pagina): mette una <b>tinta unita</b>, una <b>sfumatura</b>
(due colori, dall'alto in basso, dal basso in alto, da sinistra a destra o in diagonale) o un'<b>immagine</b> (Adatta,
Riempi, Estendi a tutta la pagina, o Centra alle dimensioni originali) dietro tutto ciò che si trova sulla pagina, con
l'opacità che scegli. Applicalo alla pagina corrente, a tutte le pagine o a pagine come 1-3, 7. Viene salvato
nel file, così tutti lo vedono, e non viene riconosciuto come testo. Aggiungere uno sfondo a una pagina
che ne ha già uno lo sostituisce. <b>Rimuovi sfondo...</b> lo toglie dalla pagina corrente, da tutte le pagine o
dalle pagine che indichi; Ctrl+Z annulla entrambe le operazioni. Uno sfondo non può trasparire da una pagina scansionata, perché
la scansione è un'immagine che copre l'intera pagina; per queste usa una Filigrana.</li>
<li><b>Esporta</b> (File &gt; Esporta in): Microsoft Word (.docx), Microsoft Excel (.xlsx),
Microsoft PowerPoint (.pptx), Disegno AutoCAD (.dxf), Immagini (PNG), Immagini (JPEG),
Testo semplice (.txt). PowerPoint crea una diapositiva per pagina con un'immagine della pagina (per
mostrarla com'è; il testo e i disegni di una diapositiva non si possono modificare come testo e
forme di PowerPoint). Le immagini sono una per pagina, con il nome che scegli più il
numero di pagina (plan_p1.png, plan_p2.png...); se qualcuna esiste già, ti viene chiesto una sola volta
prima di sostituirle.</li>
</ul>

<h2 id="accessibility">Accessibilità (tag per i lettori di schermo)</h2>
<p>Le persone cieche o ipovedenti leggono i PDF con i lettori di schermo, che seguono i
<b>tag</b> del documento: la sua struttura (titoli, paragrafi, elenchi, tabelle, figure),
l'ordine in cui leggerli e le descrizioni delle immagini. Le leggi chiedono sempre più spesso PDF
accessibili (negli Stati Uniti, il Titolo II dell'ADA per le amministrazioni statali e locali e la
Section 508 per le agenzie federali; nell'UE, l'Atto europeo sull'accessibilità); gli standard a cui
rimandano sono le WCAG 2.1 e, per i PDF, <b>PDF/UA</b> (ISO 14289-1). I comandi si trovano in
<b>Documento &gt; Accessibilità</b>; ogni modifica è un unico passo che Ctrl+Z annulla, e le
pagine restano identiche a prima.</p>
<ul>
<li><b>Verifica accessibilità...</b> elenca ciò che impedisce al documento, così com'è ora, di
essere accessibile, per tipo (il documento, il contenuto delle pagine e i tag, i titoli, gli
elenchi, le tabelle e le figure, i collegamenti e i commenti, i campi modulo, i font), ognuno con
la sua pagina (fai doppio clic su una riga per andarci), la regola che viola (la clausola di
PDF/UA e la condizione di errore del <b>Matterhorn Protocol</b>, la lista di controllo di PDF/UA
della PDF Association) e la correzione disponibile qui: seleziona la riga e fai clic su
<b>Correggi...</b>, e la verifica viene eseguita di nuovo. Controlla ciò che un programma può
controllare: il documento ha i tag, e ogni elemento di contenuto ha un tag o è contrassegnato come
artefatto (decorazione); titolo e lingua; figure e formule con testo alternativo; tabelle con celle
di intestazione che indicano a cosa fanno da intestazione; titoli che partono da H1 senza saltare
livelli; elenchi e tabelle costruiti come prevede il formato PDF; collegamenti, campi modulo e
commenti con tag e descrizione; ordine di tabulazione; font incorporati e testo leggibile come
lettere (Unicode); impostazioni di sicurezza che consentono la lettura ai lettori di schermo;
segnalibri nei documenti di più di 20 pagine (la sua correzione, <b>Crea segnalibri</b>, li crea dai
titoli dei tag in un documento con tag, altrimenti dall'aspetto dei titoli, con la stessa anteprima
di Documento &gt; Strumenti segnalibri). L'ultimo gruppo elenca ciò che solo una persona può
valutare: l'ordine di lettura ha senso, il testo alternativo dice cosa mostra ogni immagine, i
colori hanno un contrasto sufficiente (le WCAG chiedono 4,5:1, 3:1 per il testo grande), intestazioni
e piè di pagina sono artefatti, il testo riconosciuto è corretto. Per una convalida formale, usa
<b>PAC 2024</b> (gratuito, per Windows, pac.pdf-accessibility.org) o il profilo PDF/UA di
<b>veraPDF</b> (verapdf.org).</li>
<li><b>Tag automatici...</b> assegna i tag a un documento che non ne ha, ricavandoli da ciò che
disegnano le pagine: <b>titoli</b> (righe brevi più grandi o in grassetto; i livelli sono
ordinati per dimensione in tutto il documento, partono da H1 e non ne saltano mai uno),
<b>paragrafi</b>, <b>elenchi</b> (righe che iniziano con un punto elenco o un numero come 1., a)
o (iv): il punto elenco o il numero diventa l'etichetta della voce), <b>tabelle</b> disegnate con
linee attorno a ogni cella (la prima riga diventa l'intestazione delle colonne quando si distingue:
in grassetto, più grande, o parole sopra numeri), <b>figure</b> (immagini; una scansione con il
testo riconosciuto sopra è una decorazione, e viene letto il suo testo), <b>collegamenti</b> (con
le parole che coprono), <b>campi modulo</b> e <b>commenti</b>; <b>intestazioni, piè di pagina e
numeri di pagina</b> (le stesse parole in alto o in basso su molte pagine) e linee, riquadri e altri
disegni diventano <b>artefatti</b>, che i lettori di schermo saltano. L'<b>ordine di lettura</b> va
dall'alto in basso, con le colonne lette una dopo l'altra, da sinistra a destra. Chiede il titolo
e la lingua del documento (si impostano insieme). È adatto a layout semplici ed è prudente: ciò che
non riesce a riconoscere con certezza riceve il tag di paragrafo. Non riconosce gli elenchi annidati
(vengono letti come uno solo), le tabelle senza linee o con celle unite (lette come paragrafi), le
didascalie, le note a piè di pagina, le formule e i grafici disegnati con linee (artefatti: descrivili
nel testo o nel testo alternativo di una figura). Un documento che ha già i tag resta com'è. Una
pagina i cui caratteri non si possono abbinare alle istruzioni di disegno (un font insolito) riceve
il tag di un unico paragrafo, e la finestra finale lo segnala. Una pagina che ha già contenuto
contrassegnato (un programma le aveva assegnato i tag, poi rimossi, come fanno alcuni strumenti)
riceve i tag in base a quei contrassegni: ogni parte contrassegnata diventa un elemento del tipo
indicato dal contrassegno (un paragrafo quando il tipo non è standard), il resto come qualsiasi
contenuto aggiunto a una pagina con tag; la finestra indica quali pagine. Poi descrivi le figure
(Testo alternativo) ed esegui
Verifica accessibilità.</li>
<li><b>Testo alternativo...</b> elenca le figure del documento, ognuna con la sua immagine: scrivi
una descrizione (cosa mostra o a cosa serve, in una o due frasi), oppure seleziona <b>Decorativa</b>
per un'immagine che ha solo funzione decorativa: diventa un artefatto ed esce dai tag. A un
documento senza tag viene proposto prima Tag automatici (le descrizioni sono conservate nei
tag).</li>
<li><b>Ordine di lettura...</b> mostra i tag della pagina corrente, numerati nell'ordine in cui li
leggono i lettori di schermo, ognuno disegnato come un riquadro sopra un'immagine della pagina:
trascina un tag nell'elenco (o usa Sposta su e Sposta giù) per cambiare l'ordine, poi fai clic su
OK. I tag di sezioni diverse del documento restano nelle loro sezioni.</li>
<li><b>Titolo e lingua...</b>: il titolo che i lettori di schermo annunciano, scritto nelle
proprietà del documento e nei metadati XMP, e mostrato nella barra del titolo della finestra al
posto del nome del file; e la lingua del documento (English (United States), Español (España)...
o qualsiasi tag di lingua digitato), che determina la voce e la pronuncia. La lingua proposta è
quella di KanzonasPDF.</li>
<li><b>Descrizioni comando dei campi...</b>: il nome che i lettori di schermo pronunciano per ogni
campo, proposto in base alle parole subito a sinistra o sopra il campo (altrimenti in base al nome
del campo, reso leggibile): controllali e correggili nell'elenco, poi fai clic su OK.</li>
<li><b>Descrizioni dei collegamenti...</b>: ciò che i lettori di schermo pronunciano per ogni
collegamento, proposto in base alle parole che copre, altrimenti in base al suo indirizzo web o alla
pagina a cui porta.</li>
<li><b>Ordine di tabulazione secondo i tag</b>: su ogni pagina, Tab passa da un collegamento o
campo all'altro nell'ordine dei tag.</li>
<li><b>Segna come decorativo</b>: le immagini e le forme selezionate con Modifica oggetti diventano
artefatti (un'immagine con un proprio tag di figura esce dai tag). Un'immagine che condivide il tag
con del testo non si può separare da esso qui.</li>
<li><b>Incorpora font</b>: incorpora i font standard non ancora incorporati (Helvetica, Times,
Courier, Symbol, ZapfDingbats, e Arial, Times New Roman e Courier New, che vengono mostrati con
essi) usando le copie di KanzonasPDF, come fa Salva come PDF/A, così il testo ha lo stesso aspetto e
le stesse misure. Gli altri font non si possono incorporare in un secondo momento: crea di nuovo il
PDF con i font incorporati.</li>
<li><b>Identifica come PDF/UA...</b> dichiara nei metadati XMP del file che è conforme a PDF/UA-1;
fallo quando Verifica accessibilità non trova più nulla (altrimenti ti avvisa).</li>
</ul>
<p><b>Modificare un documento con tag.</b> Ogni modifica mantiene i tag allineati alle pagine,
nello stesso passo di Ctrl+Z: il testo scritto con Aggiungi testo, incollato o riscritto con
Modifica testo riceve un tag (un paragrafo, nell'ordine di lettura corrispondente al punto in cui
compare sulla pagina; un titolo, una voce di elenco o una cella di tabella riscritti restano ciò che
erano); un'immagine spostata con Modifica oggetti o in modalità CAD, anche su un'altra pagina,
conserva la sua figura e il suo testo alternativo, e un'immagine incollata è una nuova figura
(Verifica accessibilità ne chiede la descrizione); le linee e le forme aggiunte sono artefatti; le
annotazioni, i collegamenti e i campi aggiunti ricevono un tag (il popup di una nota insieme alla
sua nota, descritto dal testo della nota, come richiede la verifica PDF/UA di veraPDF), ed escono
dai tag quando li elimini; le pagine duplicate, inserite,
sostituite (Sostituisci pagine: il nuovo disegno riceve nuovi tag) o eliminate portano con sé i
loro tag; Intestazione e piè di pagina e i numeri Bates sono artefatti di impaginazione. Applica
oscuramenti (e il testo nascosto di Sanifica documento) rimuove anche il testo alternativo,
l'ActualText e l'espansione del contenuto con tag toccato da un segno, e i tag del contenuto rimosso
del tutto, così nei tag non resta nulla che riveli ciò che è stato oscurato. Quando un file
modificato da un altro programma ha tag non allineati alle pagine (contenuto senza tag, tag di
contenuto che non esiste più, un albero padre che punta nel posto sbagliato), Verifica
accessibilità lo segnala e la sua correzione <b>Ripara tag</b> sistema tutto.</p>
<p>Verifica accessibilità, Tag automatici e Testo alternativo si trovano anche nella scheda Pagine,
sotto la freccia del gruppo Documento; la tavolozza dei comandi (Ctrl+Shift+P) li trova tutti per
nome.</p>
<h2 id="batch">Elaborazione batch</h2>
<p><b>Strumenti &gt; Elaborazione batch...</b> (anche nel menu File) applica la stessa operazione a
molti PDF insieme: un ufficio rende ricercabili 200 fatture scansionate e le archivia come PDF/A,
uno studio legale applica la numerazione Bates a un insieme di documenti da produrre in causa,
RISERVATO finisce su ogni file di una cartella, le annotazioni di 40 tavole vengono appiattite, una
cartella viene ridotta abbastanza da poterla inviare per email. Non serve avere un documento aperto;
la finestra resta aperta mentre continui a lavorare.</p>
<ul>
<li><b>File:</b> <b>Aggiungi file...</b>, <b>Aggiungi cartella...</b> (i suoi PDF; seleziona
<b>Includi sottocartelle</b> per includere anche quelli delle sottocartelle), oppure trascina file e
cartelle sull'elenco. L'elenco mostra il numero di pagine di ogni file ("protetto" per un file che
richiede una password per aprirsi). I file vengono elaborati nell'ordine dell'elenco: <b>Sposta
su</b>, <b>Sposta giù</b> e <b>Ordina per nome</b> lo stabiliscono, e i numeri Bates e Combina lo
seguono. Un file aperto in una scheda viene letto com'era all'ultimo salvataggio.
<b>File protetti da password:</b> <b>Chiedi la password</b> (viene chiesta una volta: la password
viene provata per prima sui file protetti successivi, così per un gruppo di file con la stessa
password viene chiesta una sola volta; <b>Salta questo file</b> o <b>Salta tutti i file protetti</b>
li escludono) oppure <b>Saltali</b>.
Un file che si apre ma non consente modifiche richiede allo stesso modo la sua password delle
autorizzazioni. Un file con firma digitale viene saltato quando un passaggio lo modificherebbe (la
firma non sarebbe più valida).</li>
<li>I <b>passaggi</b> vengono eseguiti nell'ordine dell'elenco, ognuno con le sue opzioni (fai clic
su un passaggio per vederle; <b>Aggiungi passaggio</b>, <b>Rimuovi</b>, <b>Sposta su</b>, <b>Sposta
giù</b>). Ognuno fa esattamente ciò che fa il comando con lo stesso nome su un documento aperto:
<b>Riconosci testo (OCR)</b> (salta le pagine che hanno già testo, a meno che tu non deselezioni
l'opzione; Precisione come nella finestra dell'OCR; le pagine vengono lette dallo stesso OCR di
Riconosci testo, negli stessi piccoli blocchi e con la stessa memoria);
<b>Salva come
PDF/A</b> (dopo i passaggi che modificano il documento; possono seguirlo solo Esporta e Combina; un
file protetto da password richiede prima Rimuovi password); <b>Filigrana</b> (testo o immagine);
<b>Intestazione e piè di pagina</b> (codici {page} {pages} {date} {file} {bates}); <b>Numeri di pagina</b>;
<b>Numerazione Bates</b> (prefisso, primo numero, cifre, posizione: i numeri proseguono da un file
al successivo nell'ordine dell'elenco, quindi il primo file parte dal primo numero e ogni file
successivo da dove si è fermato il precedente; un file non riuscito o saltato non usa numeri, e il
rapporto riporta il primo e l'ultimo numero di ogni file); <b>Appiattisci commenti</b> (i segni di
oscuramento non ancora applicati restano segni, a meno che tu non scelga Applicali prima);
<b>Appiattisci campi modulo</b>
(e, se selezionato, anche commenti e annotazioni); <b>Applica oscuramenti</b> (i segni già presenti
in ogni file, applicati esattamente come fa Applica oscuramenti: le parole segnate da Cerca e oscura
vengono rimosse anche dagli altri punti del file, e nel file non resta nulla di ciò che stava sotto
un segno, né nell'ActualText di un elemento con tag, né nella miniatura della pagina, né nella copia
privata della pagina salvata da un programma); <b>Cerca e oscura</b> (un elenco di parole o frasi,
una per riga: ogni occorrenza viene segnata, anche nei livelli nascosti e dove una pagina è
ritagliata, e i segni vengono applicati, rimuovendo le parole da campi, note, collegamenti,
segnalibri, proprietà e dagli altri punti del file, come nomi dei livelli, indirizzi web, dati dei
moduli e testo alternativo, come fanno Cerca e oscura e Applica oscuramenti; una parola trovata solo
in quei punti viene rimossa da lì. Con <b>Rimuovi le informazioni nascoste</b> selezionato (anche in
Applica oscuramenti), i metadati, gli allegati, il testo nascosto, gli script e le annotazioni conservate del
tutto fuori dalle loro pagine (vedi Annotazioni fuori dalla pagina, in Primi passi) di ogni file vengono
rimossi anche se non è stato trovato nulla da oscurare; se è deselezionato, gli allegati restano e
non vengono analizzati, e il rapporto lo segnala. Applica gli oscuramenti è selezionato
all'inizio: gli originali restano com'erano
e le copie oscurate vanno nella cartella di destinazione. Il rapporto indica per ogni file cosa è
stato rimosso e da dove: le pagine, e quanti degli altri punti. Deselezionalo per segnare soltanto
le parole da rivedere: non viene ancora rimosso nulla, il rapporto lo dice ("non è stato ancora
rimosso nulla: apri il file e usa Applica oscuramenti"), e ogni file che resta con dei segni riceve
-segnato in fondo al nome, come rapporto-segnato.pdf, a meno che tu non abbia scelto un tuo modello
per il nome dei file);
<b>Sanifica documento</b> (le stesse scelte di Proteggi &gt; Sanifica documento); <b>Riduci dimensioni
file</b> (come Comprimi; un file che non diventerebbe più piccolo resta com'è); <b>Ruota pagine</b>
(tutte, dispari, pari, orizzontali o verticali, o un elenco); <b>Elimina pagine vuote</b> (pagine
senza testo e quasi senza inchiostro, come i retri bianchi di una scansione fronte-retro; una pagina
con annotazioni, campi modulo, un numero di pagina o poche parole scritte viene conservata, un file
non resta mai senza pagine, e il rapporto elenca le pagine eliminate: controllale); <b>Aggiungi password</b> e
<b>Rimuovi password</b> (come Proprietà di sicurezza; per rimuovere una password delle autorizzazioni, digitala);
<b>Imposta proprietà documento</b> (titolo, autore, oggetto, parole chiave; {name} è il nome del file);
<b>Esporta</b> (Word, Excel, PowerPoint, immagini PNG o JPEG, o testo, creati dal documento così come
l'hanno lasciato i passaggi precedenti, salvati accanto al PDF; deve venire dopo Cerca e oscura e
Applica oscuramenti, altrimenti la copia conterrebbe ancora le parole); <b>Combina tutto in un PDF</b>
(l'ultimo passaggio: i file elaborati nell'ordine dell'elenco, con un segnalibro per ciascuno;
seleziona Salva anche i singoli file per conservarli comunque; un file saltato o non riuscito non
viene incluso e non usa numeri Bates; con Cerca e oscura che segna soltanto, il file si chiama
Combinato-segnato). Il PDF di ogni file viene scritto quando i passaggi modificano i documenti; con
soli passaggi Esporta, vengono scritti solo i file esportati.</li>
<li>Le <b>sequenze</b> conservano un elenco di passaggi con le loro opzioni sotto un nome: scegline
una in <b>Sequenza</b>, usa <b>Salva sequenza...</b> per conservare i passaggi attuali, <b>Elimina
sequenza</b> per rimuovere una delle tue. Sequenze già pronte: <b>Rendi ricercabile (OCR)</b>,
<b>Archivia (OCR + PDF/A)</b>, <b>Riservato (filigrana + appiattimento)</b>, <b>Numerazione Bates per produzione documentale</b> e <b>Riduci
per email</b>. Le password digitate nei passaggi non vengono mai salvate in una sequenza. Gli ultimi
passaggi e le ultime scelte di destinazione vengono ricordati per la volta successiva.</li>
<li><b>Risultato:</b> <b>Una cartella "Elaborati" accanto a ogni file</b> (l'impostazione
predefinita), oppure <b>Questa cartella</b>, dove <b>Mantieni la struttura delle cartelle</b> mette i
file delle sottocartelle di una cartella nelle stesse sottocartelle. <b>Nome file</b>: {name} (il
nome del file stesso), {n} (il suo numero nell'elenco: 001, 002...), {date} (la data di oggi) e
{bates} (il suo primo numero Bates), per esempio {name}_ocr.
Un nome indica sempre un file nella cartella di destinazione: barre, due punti, .. e lettere di unità
diventano parte del nome, i nomi di dispositivo di Windows (CON, NUL, LPT1...) ricevono un _ davanti,
e un nome troppo lungo viene accorciato.
<b>Se il file esiste già:</b> Chiedi (Sostituisci, Sostituisci tutto, Salta, Salta tutti), Aggiungi
un numero (nome (2).pdf), Sostituiscilo o Salta il file. I risultati non sostituiscono mai i file da
cui sono stati creati, a meno che tu non selezioni <b>Consenti di sostituire i file originali</b>
(deselezionato ogni volta che apri la finestra); due file con lo stesso nome non si sovrascrivono mai
a vicenda. Una cartella "Elaborati" viene esclusa quando aggiungi di nuovo una cartella, e lo stesso
vale per i file della cartella di destinazione quando si trova dentro la cartella aggiunta (i
risultati di un'elaborazione precedente). Non viene mai scritto nulla fuori dalla cartella di
destinazione: un file già presente che è un collegamento viene sostituito, non scritto attraverso il
collegamento, e una cartella presente che è un collegamento a un altro percorso viene saltata.</li>
<li><b>Esegui</b> mostra l'avanzamento del file in elaborazione e di tutti i file. <b>Annulla</b>
completa il file in elaborazione, poi si ferma; fai di nuovo clic (<b>Interrompi subito</b>) per
fermarti subito, escludendo quel file. I risultati di un file compaiono tutti insieme o per niente:
non resta mai nulla di scritto a metà. È aperto un solo documento alla volta e la sua memoria viene
liberata prima del successivo, così un'elaborazione lunga non usa sempre più memoria.</li>
<li>Il <b>rapporto</b> finale elenca ogni file come Fatto, Ignorato o Non riuscito, con il motivo
(una password errata, un file che non è un PDF, un passaggio che non è stato possibile eseguire) e
ciò che ha scritto (dopo l'oscuramento, una parola ancora presente nel file viene segnalata come
avviso: controlla quel file);
<b>Salva rapporto...</b> lo salva come file CSV (si apre in Excel) o come testo. <b>Rapporto...</b>
lo mostra di nuovo.</li>
</ul>

<h2 id="preferences">Preferenze</h2>
<ul>
<li><b>File &gt; Preferenze...</b> (Ctrl+K) riunisce in una sola finestra le opzioni che KanzonasPDF
ricorda, con le sezioni elencate a sinistra. Un'opzione che ha anche un comando di menu fa esattamente
la stessa cosa di quel comando, quindi puoi cambiarla in tutti e due i punti. <b>OK</b> applica le
modifiche e chiude la finestra; <b>Applica</b> le applica subito e lascia la finestra aperta, così
puoi vederne l'effetto e continuare a regolare; <b>Annulla</b> la chiude senza le modifiche fatte
dopo l'ultimo Applica.</li>
<li><b>Generale:</b> tema (Come Windows, o Come il sistema su Linux e macOS; Chiaro, Scuro), <b>Lingua</b> (Automatica (la lingua di Windows),
o Automatica (la lingua del sistema); English; Español; Italiano: menu, messaggi e questo manuale; la modifica vale dal prossimo
avvio di KanzonasPDF), Barra multifunzione (al posto delle barre degli strumenti), Mostra i nomi dei gruppi sulla barra multifunzione, Mostra barra dei menu,
Mostra etichette di testo sulle barre degli strumenti, Verifica aggiornamenti automaticamente e, su Linux, Aggiungi KanzonasPDF al
menu delle applicazioni e usalo per aprire i PDF (vedi KanzonasPDF su Linux). Indica anche dove vengono salvate le tue
impostazioni (la cartella data in modalità portatile). Un'impostazione salvata che non si può usare (per
esempio, modificata a mano) viene sostituita dal suo valore predefinito. Se una impedisse comunque l'avvio di KanzonasPDF,
il programma si avvia con le impostazioni predefinite, lo segnala ed elenca quelle precedenti in
settings-before-reset.txt nella cartella data.</li>
<li><b>Utente:</b> il Nome autore delle annotazioni (registrato nelle nuove annotazioni e mostrato nei timbri), e
Configura la mia firma... / Configura la mia sigla..., con l'indicazione se ciascuna è già salvata, e Cambia PIN...
per impostare, cambiare o rimuovere il PIN che le protegge (lascia vuoto il nuovo PIN per rimuoverlo), e
la Larghezza firma e la Larghezza sigla usate quando fai clic per inserirle, e il Formato data
che scrive lo strumento Data.</li>
<li><b>Stili annotazioni:</b> scegli uno strumento a sinistra per impostarne i colori predefiniti, lo spessore della linea, la dimensione
del font, il riempimento, l'opacità e così via, le stesse impostazioni che mostra il pannello Proprietà quando quello strumento è
attivo. Ripristina predefiniti riporta uno strumento alle impostazioni originali di KanzonasPDF.</li>
<li><b>Avvio e apertura:</b> riaprire i documenti che erano aperti alla chiusura di
KanzonasPDF (disattivato per impostazione predefinita; funziona anche quando un programma di installazione chiude KanzonasPDF per
aggiornarlo, o quando Windows lo chiude per spegnersi o disconnettersi), se chiedere conferma prima di chiudere con più documenti aperti (attivato
per impostazione predefinita), lo zoom con cui si apre un
documento (Adatta larghezza per impostazione predefinita; Adatta alla pagina, la pagina intera nella finestra; Dimensioni reali; o lo zoom che aveva
alla chiusura) e se riaprirlo alla pagina in cui eri l'ultima volta.</li>
<li><b>Salvataggio:</b> ogni quanto fare il backup delle modifiche non salvate (ogni 5 minuti per impostazione predefinita; Disattivato lo
disattiva). Una copia di ogni documento con modifiche non salvate viene conservata nella cartella di backup ed eliminata quando
lo salvi o lo chiudi. Se KanzonasPDF o il computer si arrestano in modo imprevisto, all'avvio successivo ti viene proposto di aprire
le copie. Quando un programma di installazione o l'arresto di Windows (su Linux, la disconnessione o lo spegnimento) chiude KanzonasPDF, non è possibile chiedere nulla, quindi
le ultime modifiche non salvate di ogni documento vengono prima scritte nella sua copia, e all'avvio successivo vengono proposte
allo stesso modo. Ogni copia si apre in una scheda con il nome del file originale seguito da "(recuperato)", contrassegnata come
non salvata; Salva chiede dove conservarla, proponendo il file originale (o Senza titolo per un PDF che
non è mai stato salvato). Le copie proposte restano nella cartella di backup (Apri cartella di
backup) per 30 giorni. <b>Cartella di backup</b>: Cambia... sceglie un'altra cartella (se KanzonasPDF non può
scriverci, lo segnala), Usa predefinita torna a quella standard (nella cartella data in modalità
portatile). I backup dei documenti aperti passano nella nuova cartella; le copie recuperate in precedenza restano
in quella vecchia. Dei documenti protetti da password non viene fatto il backup, perché la copia non
avrebbe la password.</li>
<li><b>Misurazione:</b> le unità proposte per una pagina che non ha ancora una scala, a quale frazione arrotondare piedi e pollici
(da 1/2" a 1/64"; 1/16" per impostazione predefinita) e le cifre decimali per le altre unità. Le etichette di misura
esistenti si aggiornano la prossima volta che le sposti o le modifichi.</li>
<li><b>Mouse:</b> la modalità del mouse (<b>Standard</b>, <b>Mano</b> o <b>CAD</b>; lo strumento della modalità
è quello con cui si avvia KanzonasPDF e a cui si torna con Esc), e le opzioni di ciascuna modalità:
<ul>
<li>Standard: Scorri di una pagina per ogni scatto della rotellina (attivato), Movimento libero della pagina (disattivato).</li>
<li>Mano: Movimento libero della pagina (attivato), Scorri di una pagina per ogni scatto della rotellina (attivato), Un clic su un'annotazione con
la Mano la seleziona (attivato).</li>
<li>CAD: La rotellina esegue lo zoom sul cursore (Ctrl+rotellina scorre), Cursore a croce, Area di lavoro libera attorno alle
pagine, Selezione a finestra (blu) e intersecante (verde), Clic, sposta, clic disegna il riquadro di selezione,
Tieni premuto il pulsante e trascina per disegnare un lazo, Mostra la scheda CAD, Le lettere digitate sul disegno vanno alla
riga di comando: tutte attivate (l'ultima è disattivata per chi usava il mouse in stile CAD prima della 1.5, così
le scorciatoie degli strumenti a una lettera che usava continuano a funzionare). Con il riquadro clic, sposta, clic e il
lazo disattivati, premere, trascinare e rilasciare disegna un riquadro.</li>
</ul>
La nota sotto Scorri di una pagina per ogni scatto della rotellina indica quando si applica: solo mentre l'intera pagina
sta nella finestra, come dopo Adatta alla pagina.</li>
<li><b>Pagine e visualizzazione:</b> Blocca l'ordine delle pagine, Mostra caselle dei commenti, Evidenzia campi modulo,
Modalità notturna (linee bianche su nero), Migliora linee sottili, Mostra barra della scala, <b>Formato pagina del nuovo PDF</b> (il formato e
l'orientamento usati da File &gt; Nuovo PDF, oppure Chiedi ogni volta),
e <b>Griglia e aggancio</b>, tutto in un unico punto: spaziatura e unità della griglia, l'intervallo della linea
più scura, Mostra griglia, Aggancia alla griglia e Aggancia agli oggetti (le stesse impostazioni di Visualizza &gt; Impostazioni
griglia...).</li>
<li><b>Lettura:</b> la voce con cui legge Leggi ad alta voce (le voci installate sul computer;
l'elenco viene riempito quando lo apri) e la sua velocità, con <b>Prova</b> per ascoltarle, e la
velocità dello Scorrimento automatico.</li>
<li><b>OCR:</b> la precisione con cui si apre la finestra di dialogo Riconosci testo.</li>
<li>Le modifiche si applicano quando fai clic su OK; Annulla lascia tutto com'era.</li>
</ul>

<h2 id="shortcuts">Scorciatoie da tastiera</h2>
<table border="1" cellpadding="3" cellspacing="0">
<tr><th>Tasto</th><th>Azione</th></tr>
<tr><td>V / H</td><td>Seleziona / Mano</td></tr>
<tr><td>Ctrl+E</td><td>Modifica testo (clic: il paragrafo; Alt+clic: una riga)</td></tr>
<tr><td>Ctrl+B / Ctrl+I / Ctrl+U (durante la modifica del testo)</td><td>Grassetto / Corsivo / Sottolineato per le parole selezionate</td></tr>
<tr><td>Ctrl+] / Ctrl+[ (durante la modifica del testo)</td><td>Testo più grande / più piccolo (le parole selezionate, un punto alla volta)</td></tr>
<tr><td>Ctrl+B (fuori dalla modifica del testo)</td><td>Aggiungi segnalibro alla vista corrente</td></tr>
<tr><td>Ctrl+P</td><td>Stampa (con anteprima)</td></tr>
<tr><td>Ctrl+N</td><td>Nuovo PDF (pagina vuota)</td></tr>
<tr><td>Shift+T</td><td>Aggiungi testo (scritto nella pagina)</td></tr>
<tr><td>Ctrl+K</td><td>Preferenze</td></tr>
<tr><td>Ctrl+;</td><td>Data (la data di oggi dove fai clic)</td></tr>
<tr><td>Shift+O</td><td>Modifica oggetti (le immagini e le forme della pagina stessa)</td></tr>
<tr><td>Ctrl+Shift+H / U / X</td><td>Evidenzia / Sottolinea / Barrato</td></tr>
<tr><td>C / N / T / K</td><td>Commento / Nota / Casella di testo / Richiamo</td></tr>
<tr><td>B</td><td>Punto</td></tr>
<tr><td>R / E / O / D / Y</td><td>Rettangolo / Ellisse / Cerchio / Nuvola / Poligono</td></tr>
<tr><td>L / A / Shift+L / P</td><td>Linea / Freccia / Polilinea / Penna</td></tr>
<tr><td>M / X</td><td>Timbro / Gomma</td></tr>
<tr><td>G / I</td><td>Firma / Sigla</td></tr>
<tr><td>Shift+M / Shift+A / Shift+C</td><td>Lunghezza / Area / Conteggio</td></tr>
<tr><td>Shift+D</td><td>Quota</td></tr>
<tr><td>Shift+R</td><td>Oscura</td></tr>
<tr><td>Shift+E</td><td>Cancella contenuto</td></tr>
<tr><td>Shift+P</td><td>Cattura area</td></tr>
<tr><td>Ctrl+rotellina</td><td>Zoom attorno al puntatore (scorrimento in su e in giù nella modalità mouse CAD)</td></tr>
<tr><td>Shift+rotellina</td><td>Scorrimento a sinistra e a destra</td></tr>
<tr><td>Shift (mentre disegni)</td><td>Linee a 45&deg;, quadrati e cerchi</td></tr>
<tr><td>Shift+clic (strumento di disegno)</td><td>Inizia una nuova annotazione sopra una esistente</td></tr>
<tr><td>Ctrl+clic, Ctrl+trascinamento</td><td>Seleziona più annotazioni</td></tr>
<tr><td>Ctrl+clic su un collegamento (qualsiasi strumento, qualsiasi modalità del mouse)</td><td>Apre il collegamento, anche su un'annotazione trasformata in collegamento (un semplice clic con lo strumento Mano)</td></tr>
<tr><td>Esc</td><td>Annulla la selezione / rilascia lo strumento (torna allo strumento della modalità del mouse: Mano, Seleziona, o Modifica oggetti in modalità CAD) / annulla un comando CAD o un riquadro di selezione iniziato</td></tr>
<tr><td>Canc</td><td>Elimina ciò che è selezionato: le annotazioni e, in modalità CAD, anche gli oggetti del disegno</td></tr>
<tr><td>Ctrl+C / Ctrl+X / Ctrl+V</td><td>Copia / Taglia / Incolla (testo, annotazioni, immagini, pagine; con Modifica oggetti, le immagini, le forme e il testo della pagina stessa, su qualsiasi pagina o documento)</td></tr>
<tr><td>Ctrl+A</td><td>Seleziona tutto il testo della pagina (tutte le pagine nell'elenco delle pagine)</td></tr>
<tr><td>Ctrl+D</td><td>Duplica le annotazioni selezionate (con Modifica oggetti, il testo, le immagini e le forme selezionati; le pagine, nell'elenco delle pagine)</td></tr>
<tr><td>Canc (nell'elenco delle pagine)</td><td>Elimina le pagine selezionate</td></tr>
<tr><td>Ctrl+L</td><td>Blocca le annotazioni selezionate</td></tr>
<tr><td>Ctrl+Shift+G / Ctrl+Alt+G</td><td>Raggruppa / Separa le annotazioni selezionate, oppure le linee, forme e immagini della pagina selezionate</td></tr>
<tr><td>Ctrl+Shift+] / Ctrl+] / Ctrl+[ / Ctrl+Shift+[</td><td>Porta in primo piano / Porta avanti / Porta indietro / Porta in fondo</td></tr>
<tr><td>Left / Right, Page Up / Page Down</td><td>Pagina precedente / successiva</td></tr>
<tr><td>Home / End</td><td>Prima / ultima pagina</td></tr>
<tr><td>Ctrl+G</td><td>Vai a pagina (la casella della pagina)</td></tr>
<tr><td>Tab / Shift+Tab</td><td>Campo modulo successivo / precedente (Spazio o Invio lo compila)</td></tr>
<tr><td>Tasti freccia (con qualcosa selezionato)</td><td>Lo spostano di 1 pt; con Shift di 10 pt; con Ctrl di 0,1 pt</td></tr>
<tr><td>Ctrl+Shift+Più / Meno</td><td>Ruota la pagina</td></tr>
<tr><td>Ctrl+Shift+Up / Down</td><td>Sposta la pagina</td></tr>
<tr><td>Ctrl+2 / Ctrl+0 / Ctrl+1</td><td>Adatta alla larghezza / Adatta alla pagina / Dimensioni reali</td></tr>
<tr><td>Ctrl+F, Invio / F3, Shift+Invio / Shift+F3</td><td>Trova, risultato successivo, risultato precedente</td></tr>
<tr><td>Ctrl+H</td><td>Sostituisci testo</td></tr>
<tr><td>Ctrl+Shift+N</td><td>Sposta scheda in una nuova finestra</td></tr>
<tr><td>Alt+Down / Alt+Up</td><td>Commento successivo / precedente</td></tr>
<tr><td>F1</td><td>Questo manuale</td></tr>
<tr><td>Ctrl+Shift+P</td><td>Tavolozza dei comandi</td></tr>
<tr><td>Ctrl+F1</td><td>Comprimi / espandi la barra multifunzione</td></tr>
<tr><td>Ctrl+Shift+M</td><td>Mostra / nascondi la barra dei menu (layout con barra multifunzione)</td></tr>
<tr><td>F11</td><td>Attiva / disattiva la modalità mouse CAD (disattivandola si torna a Standard o Mano, quella che avevi)</td></tr>
<tr><td>Lettere, Invio (modalità CAD)</td><td>Digita un comando nella riga di comando (M Sposta, CO Copia, RO Ruota...); Invio lo esegue e, su una riga vuota, ripete l'ultimo. Le scorciatoie degli strumenti a una lettera non valgono in modalità CAD (quelle con Shift+lettera sì), a meno che Preferenze &gt; Mouse non disattivi la digitazione nella riga di comando.</td></tr>
<tr><td>F12</td><td>Attiva / disattiva la Modalità notturna (linee bianche su nero)</td></tr>
<tr><td>Ctrl+R</td><td>Attiva / disattiva i Righelli</td></tr>
<tr><td>Ctrl+Shift+L / F5</td><td>Schermo intero (Esc per uscire) / Presentazione</td></tr>
<tr><td>B / W / L (presentazione)</td><td>Schermo nero / schermo bianco / puntatore laser</td></tr>
<tr><td>Ctrl+5 / Ctrl+6 / Ctrl+7 / Ctrl+8</td><td>Pagina singola / Continua / Due pagine / Due pagine continue</td></tr>
<tr><td>Ctrl+4</td><td>Modalità lettura (il testo della pagina reimpaginato)</td></tr>
<tr><td>Ctrl+Shift+V / Ctrl+Shift+B</td><td>Leggi questa pagina / Leggi tutto il documento ad alta voce</td></tr>
<tr><td>Ctrl+Shift+C / Ctrl+Shift+E</td><td>Sospendi o riprendi la lettura / Interrompi la lettura ad alta voce</td></tr>
<tr><td>Ctrl+Shift+A</td><td>Scorrimento automatico (Up / Down: più lento / più veloce)</td></tr>
<tr><td>Rotellina premuta + trascinamento</td><td>Panoramica (con qualsiasi strumento)</td></tr>
<tr><td>Alt (mentre disegni o trascini)</td><td>Nessun aggancio</td></tr>
<tr><td>F4 / F6 / F7 / F8 / F9 / F10</td><td>Pagine / Proprietà / Elenco annotazioni / Cassetta degli attrezzi / Segnalibri / Vista divisa</td></tr>
</table>
<p>Puoi cambiare qualsiasi scorciatoia in Visualizza &gt; Scorciatoie da tastiera. Un tasto può essere usato da un solo comando: se due comandi condividono lo stesso tasto, non viene modificato nulla finché non risolvi il conflitto. Un tasto che hai assegnato tu a un comando resta tuo: una nuova scorciatoia predefinita che una versione successiva assegna a un altro comando non te lo toglie (quel comando resta senza scorciatoia; Ripristina tutte le impostazioni predefinite gliela restituisce). <b>Ripristina tutte le impostazioni predefinite</b> rimette subito le scorciatoie originali. Le modifiche valgono in tutte le finestre.</p>
"""
