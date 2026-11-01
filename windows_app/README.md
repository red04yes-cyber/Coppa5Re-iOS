# Coppa dei 5 Re — Windows Desktop

Applicazione desktop Windows nativa (PySide6 / Qt), offline e con dati salvati localmente.

## Funzioni principali
- Dashboard C5R, navigazione laterale con sezioni e logo nero/oro del torneo.
- Due scacchiere contemporanee con mosse legali, promozione, trascinamento pezzi o selezione a due clic.
- Scacchiere ruotabili dal punto di vista Bianco/Nero e quattro temi selezionabili.
- Controllo del tempo del torneo selezionabile tra **15+3** e **30+10**, con cronometri indipendenti, incremento dopo ogni mossa e gestione della bandierina.
- Rilevamento automatico di scacco matto, stallo, patte automatiche e patte reclamabili.
- Navigazione avanti/indietro nello storico delle mosse, annullamento ed esportazione PGN.
- Indicatori LIVE / IN CORSO / CONCLUSA e modalità streaming pulita, senza controlli amministrativi.
- Sorteggio, modifica e convalida del calendario round-robin.
- Classifica con medaglie, criteri di spareggio configurabili, statistiche testa a testa e simulazioni Monte Carlo per quote/probabilità.
- Archivio delle partite concluse e analisi delle posizioni con Stockfish.
- Playoff interattivi: semifinali, finale e finale 3°/4° posto; in caso di patta è possibile registrare il vincitore dello spareggio.
- Registro arbitro, note e incidenti; storico di modifiche a risultati e penalità; penalità modificabili e annullabili.
- Filtri di calendario per turno, giocatore e stato della partita.
- Esportazione PGN completa, classifica CSV/PDF, registro CSV e backup/ripristino JSON.
- Scorciatoie da tastiera e salvataggio automatico.

## Stockfish integrato
La build Windows scarica il pacchetto ufficiale **Stockfish 19 x86-64 universal** durante la compilazione e incorpora l'eseguibile nel programma, insieme alla licenza GPL e al riferimento al codice sorgente. L'analisi gira in background e il processo viene avviato senza finestra console visibile. Il pulsante STOCKFISH ON/OFF nella regia permette di disattivare o riattivare la valutazione. Non occorre installare né selezionare manualmente `stockfish.exe`.

La evaluation bar mostra una valutazione dal punto di vista del Bianco. La funzione Analizza partita valuta ogni posizione registrata e salva l'analisi nell'archivio locale.

Stockfish è distribuito secondo GNU GPL v3. La licenza e il riferimento alla versione sorgente sono inclusi nel bundle di compilazione.

## Quote e probabilità
Le percentuali sono stime Monte Carlo (15.000 scenari) basate sui pronostici 1-X-2 iniziali, corretti moderatamente in base alla forma osservata e ai punti/penalità del torneo. Quota equa = 1 / probabilità stimata. Non sono quote bookmaker e non suggeriscono puntate.

## Build Windows
Il workflow GitHub Actions “Build Coppa dei 5 Re for Windows”:
1. installa le dipendenze Python;
2. scarica Stockfish 19 e il relativo testo di licenza;
3. esegue test automatici su motore UCI, scacchi, calendario, quote e modalità streaming;
4. compila l'eseguibile one-file `Coppa5Re.exe` e carica l'artifact `Coppa5Re-Windows-EXE`.

## Dati locali e sviluppo
I dati sono salvati in `%APPDATA%\Coppa5Re\tournament.json`.

Per avviare in sviluppo:
1. crea un ambiente virtuale Python;
2. installa `windows_app/requirements.txt`;
3. avvia `windows_app/main.py`.

La build pubblicata è un EXE Windows. La presenza del motore integrato non equivale a una firma digitale Authenticode: Smart App Control di Windows potrebbe comunque richiedere un editore attendibile/reputazione del file.
