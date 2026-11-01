# Coppa dei 5 Re — Windows Desktop

Applicazione desktop Windows nativa (PySide6 / Qt), offline e con dati salvati localmente. Queste note riguardano esclusivamente la build Windows.

## Gestione torneo e partite
- Dashboard C5R con logo del torneo e azioni rapide per esportare, fare backup e inserire risultati arbitrali.
- Due scacchiere contemporanee con mosse legali, promozione, trascinamento pezzi o selezione a due clic.
- Scacchiere ruotabili dal punto di vista Bianco/Nero e quattro temi selezionabili.
- Cadenze fissate dal regolamento (Art. 5): qualificazione **15+3**, semifinali e finali **30+10**. Ogni orologio è indipendente; i playoff hanno pulsanti per avviare il tempo e cambiare il lato al tratto con accredito di 10 secondi.
- Rilevamento automatico di scacco matto, stallo, patta per materiale insufficiente, regola delle 75 mosse e cinque ripetizioni, oltre alle patte reclamabili tramite regola delle 50 mosse/tre ripetizioni.
- Pulsanti per patta consensuale, abbandono e forzatura arbitrale del risultato, con registrazione della terminazione e del risultato PGN formale.
- Caduta della bandierina e tempo esaurito: assegnazione del risultato in base al lato che ha esaurito il tempo, con patta se l'avversario non può dare matto per materiale insufficiente.
- Storico avanti/indietro delle mosse, annullamento, conferma prima di sovrascrivere un risultato e archivio delle partite concluse.
- Modalità streaming pulita, senza controlli amministrativi; la regia resta separata.
- Sorteggio, modifica e convalida del calendario round-robin.
- Classifica e statistiche testa a testa.

## Regolamento applicato
- Art. 8: spareggi ordinati per punti, scontro diretto (solo in parità fra due giocatori), Sonneborn–Berger e numero di vittorie. Se permane la parità, l'app segnala l'Armageddon; con tre o più giocatori segnala il mini-girone.
- Art. 11: ritiro con almeno due partite completate: i risultati già ottenuti restano validi e le partite rimanenti sono assegnate a forfait agli avversari. Con meno di due partite completate, tutti i risultati di qualificazione del giocatore ritirato vengono annullati.
- Art. 10: in caso di patta nei playoff l'app registra il pareggio e consente di annotare il vincitore dell'Armageddon. Tempi, colore e condizioni dell'Armageddon vanno approvati prima della competizione; non sono inventati dall'app.

## Precisione C5R e Stockfish
La build Windows scarica Stockfish 19 x86-64 universal durante la compilazione e incorpora il motore nell'EXE, insieme alla licenza GPL-3.0 e al riferimento al codice sorgente. Il motore è un singolo processo persistente avviato in background senza finestra console visibile. Il pulsante STOCKFISH ON/OFF nella regia permette di disattivare o riattivare le valutazioni.

La Game Review C5R assegna etichette alle mosse (brillante, migliore, ottima, buona, imprecisione, errore, grave errore), stima la perdita di punti attesi e calcola un indice di precisione locale. È un'analisi derivata da Stockfish, **non replica l'algoritmo proprietario CAPS2 né il punteggio ufficiale di Chess.com**. Le etichette e i dati disponibili vengono allegati come commenti e NAG al PGN.

## Quote e probabilità
Le percentuali sono stime Monte Carlo (15.000 scenari) basate sui pronostici 1-X-2 iniziali, corretti moderatamente in base ai risultati e alle penalità. Quota equa = 1 / probabilità stimata. Non sono quote bookmaker e non suggeriscono puntate.

## Arbitro, sicurezza dati ed esportazioni
- Registro di arbitro, note e incidenti; storico delle modifiche a risultati e penalità; penalità modificabili e annullabili.
- Recupero dopo arresto anomalo: il file temporaneo `recovery.json` viene aggiornato durante le partite; al riavvio compare una richiesta di ripristino.
- Filtri di calendario per turno, giocatore e stato della partita.
- Esportazione PGN del torneo e dei playoff, classifica CSV/PDF, registro CSV e backup/ripristino JSON.
- Scorciatoie da tastiera e salvataggio automatico.

## Build Windows
Il workflow GitHub Actions “Build Coppa dei 5 Re for Windows”:
1. installa le dipendenze Python;
2. scarica Stockfish 19 e il relativo testo di licenza;
3. esegue test automatici su motore UCI, scacchi, calendario, quote, streaming e regole del regolamento;
4. compila l'eseguibile one-file `Coppa5Re.exe` e carica l'artifact `Coppa5Re-Windows-EXE`.

## Dati locali e sviluppo
I dati sono salvati in `%APPDATA%\Coppa5Re\tournament.json`.

Per avviare in sviluppo:
1. crea un ambiente virtuale Python;
2. installa `windows_app/requirements.txt`;
3. avvia `windows_app/main.py`.

La presenza di Stockfish integrato non equivale a una firma digitale Authenticode: Smart App Control di Windows potrebbe comunque bloccare un EXE non firmato o senza reputazione sufficiente.
