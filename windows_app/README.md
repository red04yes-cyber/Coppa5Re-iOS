# Coppa dei 5 Re — Windows Desktop

Applicazione desktop Windows nativa (PySide6 / Qt), non un sito web.

## Funzioni
- Due scacchiere contemporanee e giocabili, con verifica mosse legali, scacco e promozione.
- Storico mosse, annulla mossa ed esportazione PGN.
- Calendario round-robin a 5 turni, sorteggio e modifica controllata degli accoppiamenti.
- Inserimento risultati, classifica automatica e registro penalità.
- Simulazione Monte Carlo delle probabilità e delle quote eque: 15.000 scenari, aggiornata a ogni risultato, penalità o modifica del calendario. Non sono quote bookmaker.
- Tabellone playoff provvisorio.
- Vista streaming in finestra separata e ridimensionabile: la regia rimane disponibile per continuare a registrare le mosse. Il pulsante “Torna alla regia” riporta immediatamente ai controlli.
- Evaluation bar opzionale per entrambe le scacchiere, tramite motore UCI Stockfish.
- Salvataggio automatico locale su questo PC; l'app funziona offline.

## Evaluation bar / Stockfish
L'integrazione del motore è opzionale. Per attivarla:
1. Procurati una build Windows di Stockfish compatibile con il tuo PC.
2. Premi “Configura Stockfish” sotto una delle scacchiere e seleziona `stockfish.exe`.
3. Il percorso viene salvato localmente; l'analisi viene eseguita in background a profondità 12, senza bloccare l'interfaccia.

In alternativa, l'app rileva automaticamente `stockfish.exe` se si trova accanto all'eseguibile o in `%APPDATA%\Coppa5Re\`. Il motore non è incluso nell'EXE in questa build: va fornito separatamente. La barra mostra una stima del vantaggio dal punto di vista del Bianco e una percentuale indicativa, non una probabilità ufficiale di vittoria.

## Generare l'EXE
Il workflow GitHub Actions “Build Coppa dei 5 Re for Windows” compila l'app su un runner Windows e carica l'artifact “Coppa5Re-Windows-EXE”.

## Avvio locale per sviluppo
1. Crea un ambiente virtuale Python.
2. Installa `windows_app/requirements.txt`.
3. Avvia `windows_app/main.py`.

I dati locali sono salvati in `%APPDATA%\Coppa5Re\tournament.json`.

Le probabilità e le quote sono stime simulate, non quote bookmaker e non gestiscono denaro o puntate reali.
