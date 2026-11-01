# Coppa dei 5 Re — Windows Desktop

Applicazione desktop Windows nativa (PySide6 / Qt), non un sito web.

## Funzioni
- Due scacchiere contemporanee e giocabili.
- Verifica delle mosse legali, scacco e promozione.
- Storico mosse, annulla mossa ed esportazione PGN.
- Calendario a 5 turni, inserimento risultati e classifica automatica.
- Registro penalità con detrazione configurabile di punti.
- Simulazione di quote e probabilità aggiornate a ogni risultato.
- Tabellone playoff provvisorio.
- Modalità spettatore a schermo intero per acquisizione con OBS o Discord.
- Salvataggio automatico locale su questo PC; l'app funziona offline.

## Generare l'EXE
Il workflow GitHub Actions “Build Coppa dei 5 Re for Windows” compila l'app su un runner Windows e carica l'artifact “Coppa5Re-Windows-EXE”.

## Avvio locale per sviluppo
1. Crea un ambiente virtuale Python.
2. Installa il file windows_app/requirements.txt.
3. Avvia windows_app/main.py.

I dati locali sono salvati in %APPDATA%\Coppa5Re\tournament.json.

Le quote sono stime eque simulate, non quote bookmaker e non gestiscono denaro o puntate reali.
