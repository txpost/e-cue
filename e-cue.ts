import { readFileSync, writeFileSync } from 'fs';
import { createInterface } from 'readline';
import { execSync } from 'child_process';
import { platform } from 'os';
import { program } from 'commander';
import ollama from 'ollama';

const MODEL = "llama3:latest";

// ANSI color codes
const COLOR_RESET = "\x1b[0m";
const COLOR_USER = "\x1b[96m";  // Bright cyan
const COLOR_E_CUE = "\x1b[92m";  // Bright green


// ==============================
// Spinner animation
// ==============================
class Spinner {
    private static spinnerCycle = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
    private currentIndex = 0;
    private message: string;
    private intervalId: NodeJS.Timeout | null = null;

    constructor(message: string = "Thinking") {
        this.message = message;
    }

    private getNextChar(): string {
        const char = Spinner.spinnerCycle[this.currentIndex];
        this.currentIndex = (this.currentIndex + 1) % Spinner.spinnerCycle.length;
        return char;
    }

    private initSpinner(): void {
        this.intervalId = setInterval(() => {
            process.stdout.write(`\r${this.message} ${this.getNextChar()}`);
        }, 100);
    }

    start(): void {
        this.initSpinner();
    }

    stop(): void {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }
        const clearLength = this.message.length + 4;
        process.stdout.write("\r" + " ".repeat(clearLength) + "\r");
    }
}


// ==============================
// File handling
// ==============================
function loadJson<T>(filename: string, defaultValue: T): T {
    try {
        const content = readFileSync(filename, 'utf-8');
        return JSON.parse(content);
    } catch (error) {
        return defaultValue;
    }
}

function saveJson(filename: string, data: any): void {
    writeFileSync(filename, JSON.stringify(data, null, 2));
}

function loadPersona(personaFile: string): string {
    try {
        const content = readFileSync(personaFile, 'utf-8');
        return content.trim();
    } catch (error) {
        console.error(`[error] Persona file '${personaFile}' not found.`);
        process.exit(1);
    }
}

interface JournalEntry {
    timestamp: string;
    persona_file: string;
    word_count: number;
    exchanges: Array<{ user: string; "e-cue": string }>;
}

interface JournalMetadata {
    current_daily_streak: number;
    all_time_daily_streak: number;
    total_word_count: number;
    average_word_count_per_day: number;
    average_word_count_per_session: number;
    total_entries: number;
    last_entry_date: string | null;
}

interface JournalData {
    metadata?: JournalMetadata;
    entries: JournalEntry[];
}

function loadJournal(): JournalData {
    const defaultData: JournalData = {
        metadata: {
            current_daily_streak: 0,
            all_time_daily_streak: 0,
            total_word_count: 0,
            average_word_count_per_day: 0,
            average_word_count_per_session: 0,
            total_entries: 0,
            last_entry_date: null,
        },
        entries: [],
    };
    const data = loadJson<JournalData>("journal.json", defaultData);

    // Ensure metadata exists, initialize if missing
    if (!data.metadata) {
        data.metadata = defaultData.metadata!;
    }

    // Calculate metadata from existing entries if entries exist
    if (data.entries && data.entries.length > 0) {
        data.metadata = calculateMetadata(data.entries);
    }

    return data;
}

function calculateMetadata(entries: JournalEntry[]): JournalMetadata {
    if (entries.length === 0) {
        return {
            current_daily_streak: 0,
            all_time_daily_streak: 0,
            total_word_count: 0,
            average_word_count_per_day: 0,
            average_word_count_per_session: 0,
            total_entries: 0,
            last_entry_date: null,
        };
    }

    const MIN_WORDS_FOR_STREAK = 750;

    // Calculate total word count and track dates with qualifying sessions (750+ words)
    let totalWordCount = 0;
    const dates = new Set<string>();
    const qualifyingDates = new Set<string>(); // Dates with at least one 750+ word session
    const dateWordCounts = new Map<string, number>(); // Track total words per day
    let lastEntryDate: string | null = null;

    for (const entry of entries) {
        const wordCount = entry.word_count || 0;
        totalWordCount += wordCount;

        // Extract date from timestamp (format: "2025-11-18 13:58:26")
        const dateStr = entry.timestamp.split(' ')[0];
        dates.add(dateStr);

        // Track total words per day
        dateWordCounts.set(dateStr, (dateWordCounts.get(dateStr) || 0) + wordCount);

        // Track dates with at least one qualifying session (750+ words)
        if (wordCount >= MIN_WORDS_FOR_STREAK) {
            qualifyingDates.add(dateStr);
        }

        // Track most recent entry date
        if (!lastEntryDate || entry.timestamp > lastEntryDate) {
            lastEntryDate = dateStr;
        }
    }

    // Calculate averages
    const averageWordCountPerSession = totalWordCount / entries.length;
    const uniqueDaysCount = dates.size;
    const averageWordCountPerDay = uniqueDaysCount > 0 ? totalWordCount / uniqueDaysCount : 0;

    // Sort qualifying dates for streak calculation
    const sortedQualifyingDates = Array.from(qualifyingDates).sort();

    // Calculate current daily streak (consecutive days ending today with 750+ word session)
    const today = new Date();
    const todayStr = today.toISOString().split('T')[0];

    let currentStreak = 0;
    // Only count streak if there's a qualifying entry today
    if (qualifyingDates.has(todayStr)) {
        // Check backwards from today
        const checkDate = new Date(today);
        let streakDate = todayStr;

        while (qualifyingDates.has(streakDate)) {
            currentStreak++;
            checkDate.setDate(checkDate.getDate() - 1);
            streakDate = checkDate.toISOString().split('T')[0];
        }
    }

    // Calculate all-time daily streak (longest consecutive period with 750+ word sessions)
    let allTimeStreak = 0;
    if (sortedQualifyingDates.length > 0) {
        let maxStreak = 1;
        let currentConsecutive = 1;

        for (let i = 1; i < sortedQualifyingDates.length; i++) {
            const prevDate = new Date(sortedQualifyingDates[i - 1]);
            const currDate = new Date(sortedQualifyingDates[i]);
            const diffDays = Math.floor((currDate.getTime() - prevDate.getTime()) / (1000 * 60 * 60 * 24));

            if (diffDays === 1) {
                // Consecutive day
                currentConsecutive++;
                maxStreak = Math.max(maxStreak, currentConsecutive);
            } else {
                // Gap found, reset counter
                currentConsecutive = 1;
            }
        }

        allTimeStreak = maxStreak;
    }

    return {
        current_daily_streak: currentStreak,
        all_time_daily_streak: allTimeStreak,
        total_word_count: totalWordCount,
        average_word_count_per_day: Math.round(averageWordCountPerDay * 100) / 100, // Round to 2 decimal places
        average_word_count_per_session: Math.round(averageWordCountPerSession * 100) / 100, // Round to 2 decimal places
        total_entries: entries.length,
        last_entry_date: lastEntryDate,
    };
}

function countWords(text: string): number {
    /** Count words in a text string. */
    return text.trim() ? text.split(/\s+/).length : 0;
}


// ==============================
// Main journaling loop
// ==============================
async function journalLoop(personaFile: string): Promise<void> {
    // Clear the terminal screen
    const clearCommand = platform() === 'win32' ? 'cls' : 'clear';
    execSync(clearCommand, { stdio: 'inherit' });

    const persona = loadPersona(personaFile);
    const journalData = loadJournal();

    const systemPrompt = persona;
    const messages: Array<{ role: string; content: string }> = [
        { role: "system", content: systemPrompt }
    ];

    console.log(`Journaling with persona: ${personaFile}`);
    console.log("Type 'save' to save and exit, or 'exit'/'quit' to end without saving.\n");

    let cumulativeWords = 0;
    const sessionStartTime = new Date();
    const sessionExchanges: Array<{ user: string; "e-cue": string }> = [];

    const rl = createInterface({
        input: process.stdin,
        output: process.stdout,
    });

    const question = (prompt: string): Promise<string> => {
        return new Promise((resolve) => {
            rl.question(prompt, resolve);
        });
    };

    while (true) {
        const userInput = (await question(`${COLOR_USER}You:${COLOR_RESET} `)).trim();
        if (!userInput) {
            continue;
        }
        if (userInput.toLowerCase() === "exit" || userInput.toLowerCase() === "quit") {
            console.log("\nEnding journal session (not saved).");
            break;
        }
        if (userInput.toLowerCase() === "save") {
            // Save session as a single entry
            if (sessionExchanges.length > 0) {
                const sessionEntry: JournalEntry = {
                    timestamp: sessionStartTime.toISOString().replace('T', ' ').slice(0, 19),
                    persona_file: personaFile,
                    word_count: cumulativeWords,
                    exchanges: sessionExchanges,
                };
                if (!journalData.entries) {
                    journalData.entries = [];
                }
                journalData.entries.push(sessionEntry);

                // Calculate and update metadata
                journalData.metadata = calculateMetadata(journalData.entries);

                saveJson("journal.json", journalData);
                console.log(`\n${COLOR_E_CUE}✓ Saved session with ${sessionExchanges.length} exchanges to journal.${COLOR_RESET}\n`);
            } else {
                console.log(`\n${COLOR_E_CUE}No entries to save.${COLOR_RESET}\n`);
            }
            console.log("Ending journal session.");
            break;
        }

        // Show cumulative word count after input
        const wordCount = countWords(userInput);
        cumulativeWords += wordCount;
        console.log(`${COLOR_USER}[${wordCount} words this entry, ${cumulativeWords} words total]${COLOR_RESET}`);

        messages.push({ role: "user", content: userInput });

        const spinner = new Spinner();
        spinner.start();
        try {
            const response = await ollama.chat({
                model: MODEL,
                messages: messages as any,
            });
            spinner.stop();

            const aiMessage = response.message.content.trim();
            console.log(`\n${COLOR_E_CUE}e-cue:${COLOR_RESET} ${aiMessage}\n`);
            messages.push({ role: "e-cue", content: aiMessage });

            // Store exchange in session (not saved yet)
            const exchange = {
                user: userInput,
                "e-cue": aiMessage,
            };
            sessionExchanges.push(exchange);
        } catch (e: any) {
            spinner.stop();
            console.error(`\n[error] ${e}`);
            continue;
        }
    }

    rl.close();
}

function main(): void {
    program
        .description("Journal with different personas")
        .option(
            "--persona <path>",
            "Path to persona file (default: persona.txt)",
            "persona.txt"
        );

    program.parse();
    const options = program.opts();

    journalLoop(options.persona).catch((error) => {
        console.error("Fatal error:", error);
        process.exit(1);
    });
}

if (require.main === module) {
    main();
}

