import SwiftUI

struct Player: Identifiable {
    let id: String
    let name: String
    let username: String
    let rating: String
    let note: String
}

struct Game: Identifiable {
    let id: String
    let round: Int
    let white: String
    let black: String
}

struct Standing: Identifiable {
    let id: String
    let points: Double
    let wins: Int
    let draws: Int
    let losses: Int
    let played: Int
}

@MainActor
final class TournamentStore: ObservableObject {
    @Published var results: [String: String] {
        didSet {
            if let data = try? JSONEncoder().encode(results) {
                UserDefaults.standard.set(data, forKey: storageKey)
            }
        }
    }

    private let storageKey = "coppa5re.results.v1"

    let players: [Player] = [
        Player(id: "simone", name: "Simone", username: "Easyclapp0", rating: "circa 1200", note: "Rating dichiarato; repertorio 1.d4 e Caro-Kann."),
        Player(id: "roberto", name: "Roberto", username: "chuckyn0", rating: "1304 · 20 ott 2026", note: "Rating storico, non necessariamente attuale."),
        Player(id: "matteo", name: "Matteo", username: "mmathoo", rating: "1062 · 23 ott 2026", note: "Rating storico. H2H aggiornato comunicato: 3–3."),
        Player(id: "jacopo", name: "Jacopo", username: "jjand1", rating: "774 · 28 set 2026", note: "Rating storico; H2H ufficiale indicato: 1–2."),
        Player(id: "lotario", name: "Lotario", username: "LotarioDettori", rating: "circa 580 · lug 2025", note: "Rating molto datato; nessun H2H quantificato nel PGN esaminato.")
    ]

    let games: [Game] = [
        Game(id: "R1-M1", round: 1, white: "jacopo", black: "roberto"),
        Game(id: "R1-M2", round: 1, white: "lotario", black: "matteo"),
        Game(id: "R2-M1", round: 2, white: "simone", black: "roberto"),
        Game(id: "R2-M2", round: 2, white: "lotario", black: "jacopo"),
        Game(id: "R3-M1", round: 3, white: "matteo", black: "simone"),
        Game(id: "R3-M2", round: 3, white: "roberto", black: "lotario"),
        Game(id: "R4-M1", round: 4, white: "simone", black: "lotario"),
        Game(id: "R4-M2", round: 4, white: "matteo", black: "jacopo"),
        Game(id: "R5-M1", round: 5, white: "jacopo", black: "simone"),
        Game(id: "R5-M2", round: 5, white: "roberto", black: "matteo")
    ]

    let byes: [Int: String] = [1: "simone", 2: "matteo", 3: "jacopo", 4: "roberto", 5: "lotario"]

    init() {
        if let data = UserDefaults.standard.data(forKey: storageKey),
           let saved = try? JSONDecoder().decode([String: String].self, from: data) {
            results = saved
        } else {
            results = [:]
        }
    }

    func player(_ id: String) -> Player {
        players.first(where: { $0.id == id }) ?? players[0]
    }

    func standings() -> [Standing] {
        let rows = players.map { player in
            var points = 0.0
            var wins = 0
            var draws = 0
            var losses = 0
            var played = 0

            for game in games where game.white == player.id || game.black == player.id {
                guard let result = results[game.id] else { continue }
                played += 1
                if result == "½–½" {
                    points += 0.5
                    draws += 1
                } else if (result == "1–0" && game.white == player.id) ||
                            (result == "0–1" && game.black == player.id) {
                    points += 1
                    wins += 1
                } else {
                    losses += 1
                }
            }
            return Standing(id: player.id, points: points, wins: wins, draws: draws, losses: losses, played: played)
        }

        let order = Dictionary(uniqueKeysWithValues: players.enumerated().map { ($0.element.id, $0.offset) })
        return rows.sorted {
            if $0.points != $1.points { return $0.points > $1.points }
            return (order[$0.id] ?? 99) < (order[$1.id] ?? 99)
        }
    }

    func unfinishedGames() -> [Game] {
        games.filter { results[$0.id] == nil }
    }
}

@main
struct Coppa5ReApp: App {
    @StateObject private var store = TournamentStore()
    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .preferredColorScheme(.dark)
        }
    }
}

struct RootView: View {
    var body: some View {
        TabView {
            DashboardView().tabItem { Label("Home", systemImage: "crown.fill") }
            CalendarView().tabItem { Label("Calendario", systemImage: "calendar") }
            StandingsView().tabItem { Label("Classifica", systemImage: "list.number") }
            ForecastView().tabItem { Label("Pronostici", systemImage: "chart.bar.xaxis") }
            PlayersView().tabItem { Label("Giocatori", systemImage: "person.2.fill") }
            PlayoffView().tabItem { Label("Playoff", systemImage: "trophy.fill") }
        }
        .tint(Color(red: 0.9, green: 0.7, blue: 0.3))
    }
}

struct MetricCard: View {
    let title: String
    let value: String
    let symbol: String
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Image(systemName: symbol).foregroundStyle(.yellow)
            Text(value).font(.title2.bold()).monospacedDigit()
            Text(title).font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(Color.white.opacity(0.055), in: RoundedRectangle(cornerRadius: 14))
    }
}

struct DashboardView: View {
    @EnvironmentObject var store: TournamentStore
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("COPPA DEI 5 RE").font(.caption.weight(.heavy)).tracking(3).foregroundStyle(.yellow)
                        Text("La sfida è aperta").font(.largeTitle.bold())
                        Text("Round-robin · 5 turni · dal 15 novembre 2026")
                            .font(.subheadline).foregroundStyle(.secondary)
                    }
                    HStack(spacing: 10) {
                        MetricCard(title: "Partite concluse", value: "\(store.results.count)/10", symbol: "checkmark.circle")
                        MetricCard(title: "Giocatori", value: "5", symbol: "person.3")
                        MetricCard(title: "Da giocare", value: "\(store.unfinishedGames().count)", symbol: "clock")
                    }
                    Text("CLASSIFICA PROVVISORIA").font(.caption.bold()).tracking(1.2).foregroundStyle(.yellow)
                    StandingsTable(compact: true)
                    Text("PROSSIMI INCONTRI").font(.caption.bold()).tracking(1.2).foregroundStyle(.yellow)
                    ForEach(store.unfinishedGames().prefix(3)) { game in GameRow(game: game) }
                    if store.results.isEmpty {
                        Text("Inserisci il primo risultato dal Calendario. La classifica si aggiornerà automaticamente.")
                            .font(.footnote).foregroundStyle(.secondary)
                            .padding().frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 14))
                    }
                }.padding()
            }
            .background(Color(red: 0.055, green: 0.06, blue: 0.075))
            .navigationTitle("Coppa dei 5 Re")
        }
    }
}

struct CalendarView: View {
    @EnvironmentObject var store: TournamentStore
    var body: some View {
        NavigationStack {
            List {
                ForEach(1...5, id: \.self) { round in
                    Section("Turno \(round)") {
                        ForEach(store.games.filter { $0.round == round }) { game in
                            GameRow(game: game)
                        }
                        HStack {
                            Image(systemName: "moon.zzz").foregroundStyle(.yellow)
                            Text("Riposa: \(store.player(store.byes[round] ?? "simone").name)")
                            Spacer()
                            Text("Bye").font(.caption).foregroundStyle(.secondary)
                        }.padding(.vertical, 5)
                    }
                }
            }
            .scrollContentBackground(.hidden)
            .background(Color(red: 0.055, green: 0.06, blue: 0.075))
            .navigationTitle("Calendario")
        }
    }
}

struct GameRow: View {
    @EnvironmentObject var store: TournamentStore
    let game: Game
    @State private var editing = false
    var body: some View {
        Button { editing = true } label: {
            HStack(spacing: 10) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(store.player(game.white).name + "  (Bianco)").font(.subheadline.weight(.semibold))
                    Text(store.player(game.black).name + "  (Nero)").font(.subheadline.weight(.semibold))
                }
                Spacer()
                Text(store.results[game.id] ?? "Da giocare")
                    .font(.subheadline.bold())
                    .foregroundStyle(store.results[game.id] == nil ? .secondary : .yellow)
                Image(systemName: "chevron.right").font(.caption).foregroundStyle(.tertiary)
            }.contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .sheet(isPresented: $editing) { ResultEditor(game: game) }
    }
}

struct ResultEditor: View {
    @EnvironmentObject var store: TournamentStore
    @Environment(\.dismiss) private var dismiss
    let game: Game
    @State private var selection = "1–0"

    var body: some View {
        NavigationStack {
            Form {
                Section("Incontro") {
                    LabeledContent("Bianco", value: store.player(game.white).name)
                    LabeledContent("Nero", value: store.player(game.black).name)
                }
                Section("Risultato") {
                    Picker("Esito", selection: $selection) {
                        Text("Vince il Bianco · 1–0").tag("1–0")
                        Text("Patta · ½–½").tag("½–½")
                        Text("Vince il Nero · 0–1").tag("0–1")
                    }.pickerStyle(.inline)
                }
                if store.results[game.id] != nil {
                    Section {
                        Button("Annulla risultato", role: .destructive) {
                            store.results.removeValue(forKey: game.id)
                            dismiss()
                        }
                    }
                }
            }
            .navigationTitle("Inserisci risultato")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Annulla") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Salva") { store.results[game.id] = selection; dismiss() }
                }
            }
            .onAppear { selection = store.results[game.id] ?? "1–0" }
        }
        .preferredColorScheme(.dark)
    }
}

struct StandingsView: View {
    var body: some View {
        NavigationStack {
            StandingsTable(compact: false)
                .padding()
                .background(Color(red: 0.055, green: 0.06, blue: 0.075))
                .navigationTitle("Classifica")
        }
    }
}

struct StandingsTable: View {
    @EnvironmentObject var store: TournamentStore
    let compact: Bool
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("#").frame(width: 24, alignment: .leading)
                Text("Giocatore").frame(maxWidth: .infinity, alignment: .leading)
                Text("Pt").frame(width: 34, alignment: .trailing)
                if !compact { Text("V-P-S").frame(width: 68, alignment: .trailing) }
                Text("G").frame(width: 24, alignment: .trailing)
            }.font(.caption2.bold()).foregroundStyle(.secondary).padding(.vertical, 9)

            ForEach(Array(store.standings().enumerated()), id: \.element.id) { index, row in
                Divider().overlay(.white.opacity(0.08))
                HStack {
                    Text("\(index + 1)").foregroundStyle(index == 0 ? .yellow : .secondary).frame(width: 24, alignment: .leading)
                    Text(store.player(row.id).name).font(.subheadline.weight(.semibold)).frame(maxWidth: .infinity, alignment: .leading)
                    Text(row.points.formatted(.number.precision(.fractionLength(0...1))))
                        .font(.subheadline.bold()).foregroundStyle(.yellow).frame(width: 34, alignment: .trailing)
                    if !compact {
                        Text("\(row.wins)-\(row.draws)-\(row.losses)")
                            .font(.caption.monospacedDigit()).frame(width: 68, alignment: .trailing)
                    }
                    Text("\(row.played)").font(.caption.monospacedDigit()).foregroundStyle(.secondary).frame(width: 24, alignment: .trailing)
                }.padding(.vertical, 11)
            }
            Text("Vittoria 1 · Patta 0,5 · Sconfitta 0. I pari merito restano condivisi finché non viene definito uno spareggio.")
                .font(.caption2).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading).padding(.top, 12)
        }
        .padding(14)
        .background(Color.white.opacity(0.045), in: RoundedRectangle(cornerRadius: 16))
    }
}

struct ForecastView: View {
    let forecasts: [(String, String, Int, Int, Int)] = [
        ("Jacopo", "Roberto", 10, 13, 77),
        ("Lotario", "Matteo", 12, 18, 70),
        ("Simone", "Roberto", 43, 18, 39),
        ("Lotario", "Jacopo", 22, 20, 58),
        ("Matteo", "Simone", 25, 15, 60),
        ("Roberto", "Lotario", 78, 14, 8),
        ("Simone", "Lotario", 72, 15, 13),
        ("Matteo", "Jacopo", 56, 20, 24),
        ("Jacopo", "Simone", 10, 12, 78),
        ("Roberto", "Matteo", 60, 18, 22)
    ]

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Text("Stime soggettive iniziali: non sono probabilità validate né quote offerte da bookmaker.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                Section("Pronostici 1X2") {
                    ForEach(Array(forecasts.enumerated()), id: \.offset) { _, item in
                        VStack(alignment: .leading, spacing: 8) {
                            HStack { Text(item.0).fontWeight(.semibold); Spacer(); Text(item.1).fontWeight(.semibold) }
                            HStack(spacing: 5) {
                                ProbabilityBar(value: item.2, label: "1")
                                ProbabilityBar(value: item.3, label: "X")
                                ProbabilityBar(value: item.4, label: "2")
                            }
                            HStack {
                                Text("1  \(item.2)%"); Spacer()
                                Text("X  \(item.3)%"); Spacer()
                                Text("2  \(item.4)%")
                            }.font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
                        }.padding(.vertical, 5)
                    }
                }
                Section("Vincitore finale · quote teoriche") {
                    ForEach([("Roberto", "2,50"), ("Simone", "3,00"), ("Matteo", "5,50"), ("Jacopo", "9,00"), ("Lotario", "26,00")], id: \.0) { item in
                        LabeledContent(item.0, value: item.1)
                    }
                    Text("Valori illustrativi, non aggiornati e non utilizzabili come offerte reali.")
                        .font(.caption2).foregroundStyle(.secondary)
                }
            }
            .scrollContentBackground(.hidden)
            .background(Color(red: 0.055, green: 0.06, blue: 0.075))
            .navigationTitle("Pronostici")
        }
    }
}

struct ProbabilityBar: View {
    let value: Int
    let label: String
    var body: some View {
        VStack(spacing: 3) {
            GeometryReader { proxy in
                ZStack(alignment: .leading) {
                    Capsule().fill(.white.opacity(0.08))
                    Capsule().fill(Color.yellow.opacity(0.85))
                        .frame(width: proxy.size.width * CGFloat(value) / 100)
                }
            }.frame(height: 7)
            Text(label).font(.caption2).foregroundStyle(.secondary)
        }
    }
}

struct PlayersView: View {
    @EnvironmentObject var store: TournamentStore
    var body: some View {
        NavigationStack {
            List(store.players) { player in
                VStack(alignment: .leading, spacing: 5) {
                    HStack {
                        Text(player.name).font(.headline)
                        Spacer()
                        Text(player.rating).font(.caption.monospacedDigit()).foregroundStyle(.yellow)
                    }
                    Text(player.username).font(.caption).foregroundStyle(.secondary)
                    Text(player.note).font(.footnote).foregroundStyle(.secondary)
                }.padding(.vertical, 7)
            }
            .scrollContentBackground(.hidden)
            .background(Color(red: 0.055, green: 0.06, blue: 0.075))
            .navigationTitle("Giocatori")
        }
    }
}

struct PlayoffView: View {
    var body: some View {
        NavigationStack {
            List {
                Section("Semifinali") {
                    LabeledContent("Semifinale 1", value: "1° classificato vs 4°")
                    LabeledContent("Semifinale 2", value: "2° classificato vs 3°")
                }
                Section("Finali") {
                    LabeledContent("Finale", value: "Vincitori semifinali")
                    LabeledContent("3°/4° posto", value: "Sconfitti semifinali")
                }
                Section {
                    Text("Gli accoppiamenti si definiranno alla conclusione del girone. Nessuno spareggio viene inventato in caso di pari merito.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            .scrollContentBackground(.hidden)
            .background(Color(red: 0.055, green: 0.06, blue: 0.075))
            .navigationTitle("Playoff")
        }
    }
}
