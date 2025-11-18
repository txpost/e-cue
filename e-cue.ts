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

function loadJournal(): { entries: any[] } {
    return loadJson("journal.json", { entries: [] });
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
                const sessionEntry = {
                    timestamp: sessionStartTime.toISOString().replace('T', ' ').slice(0, 19),
                    persona_file: personaFile,
                    word_count: cumulativeWords,
                    exchanges: sessionExchanges,
                };
                if (!journalData.entries) {
                    journalData.entries = [];
                }
                journalData.entries.push(sessionEntry);
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

