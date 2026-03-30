import sys
import math
import json
import pygame


# =========================
# Loading Assets (Placeholders)
# =========================
def safe_load_image(path, size, fallback_color):
    try:
        image = pygame.image.load(path).convert()
        return pygame.transform.scale(image, size)
    except Exception:
        surface = pygame.Surface(size)
        surface.fill(fallback_color)
        return surface


def make_tone_sound(frequency=440, duration_ms=120, volume=0.3):
    sample_rate = 44100
    length = int(sample_rate * (duration_ms / 1000.0))
    buf = bytearray()
    for i in range(length):
        t = i / sample_rate
        sample = int(32767 * volume * math.sin(2 * math.pi * frequency * t))
        buf += int(sample).to_bytes(2, byteorder="little", signed=True)
    return pygame.mixer.Sound(buffer=buf)


# =========================
# Level Selection and Save Data
# =========================
class LevelManager:
    def __init__(self, data_path="cyberlock_progress.json"):
        self.data_path = data_path
        self.difficulties = ["Easy", "Medium", "Hard"]
        self.level_counts = {"Easy": 30, "Medium": 30, "Hard": 20}
        self.data = self._default_data()
        self.load()

    def _default_data(self):
        data = {}
        for diff in self.difficulties:
            count = self.level_counts[diff]
            data[diff] = {
                "unlocked": [True] + [False] * (count - 1),
                "completed": [False] * count,
                "current_level": 1,
            }
        data["stats"] = {
            "correct": 0,
            "hints_used": 0,
            "badges": [],
            "levels_completed": 0,
        }
        return data

    def load(self):
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        except Exception:
            self.data = self._default_data()
            self.save()

    def save(self):
        with open(self.data_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    def is_unlocked(self, difficulty, level_index):
        return self.data[difficulty]["unlocked"][level_index]

    def complete_level(self, difficulty, level_index):
        self.data[difficulty]["completed"][level_index] = True
        if level_index + 1 < self.level_counts[difficulty]:
            self.data[difficulty]["unlocked"][level_index + 1] = True
        self.data[difficulty]["current_level"] = min(level_index + 2, self.level_counts[difficulty])
        self.data["stats"]["levels_completed"] += 1
        self.save()

    def add_badge(self, badge_name):
        if badge_name not in self.data["stats"]["badges"]:
            self.data["stats"]["badges"].append(badge_name)
            self.save()


# =========================
# HUD (Scoreboard, Timer)
# =========================
class HUD:
    def __init__(self, font):
        self.font = font
        self.panel_rect = pygame.Rect(10, 10, 350, 120)

    def draw(self, surface, state):
        pygame.draw.rect(surface, (20, 20, 20), self.panel_rect, border_radius=6)
        pygame.draw.rect(surface, (80, 80, 80), self.panel_rect, 2, border_radius=6)

        lines = [
            f"Difficulty: {state['difficulty']}",
            f"Level: {state['level']}",
            f"Time Left: {state['time_left_mmss']}",
            f"Accuracy: {state['correct']}",
            f"Hints Used: {state['hints_used']}",
        ]
        for i, text in enumerate(lines):
            label = self.font.render(text, True, (230, 230, 230))
            surface.blit(label, (20, 18 + i * 20))


# =========================
# Inventory / Clue Bar
# =========================
class Inventory:
    def __init__(self, font):
        self.font = font
        self.items = []

    def add(self, item):
        if item not in self.items:
            self.items.append(item)

    def clear(self):
        self.items = []

    def draw(self, surface):
        bar_rect = pygame.Rect(0, 550, 900, 50)
        pygame.draw.rect(surface, (15, 15, 15), bar_rect)
        pygame.draw.rect(surface, (70, 70, 70), bar_rect, 2)
        text = "Inventory: " + ", ".join(self.items) if self.items else "Inventory: (empty)"
        label = self.font.render(text, True, (200, 200, 200))
        surface.blit(label, (20, 563))


# =========================
# Hint System (Tiered)
# =========================
class HintSystem:
    def __init__(self, font):
        self.font = font
        self.popup_text = ""
        self.popup_timer = 0
        self.level_index = 0

    def request_hint(self, puzzle, game):
        if self.popup_timer > 0:
            return
        hint = puzzle.get_hint(self.level_index)
        if hint:
            self.popup_text = hint
            self.popup_timer = 180
            self.level_index = min(self.level_index + 1, 2)
            game.use_hint_penalty()

    def reset(self):
        self.popup_text = ""
        self.popup_timer = 0
        self.level_index = 0

    def draw(self, surface):
        if self.popup_timer > 0:
            pygame.draw.rect(surface, (10, 10, 10), (180, 120, 540, 80))
            pygame.draw.rect(surface, (150, 150, 150), (180, 120, 540, 80), 2)
            text = self.font.render(f"Hint: {self.popup_text}", True, (230, 230, 230))
            surface.blit(text, (200, 150))
            self.popup_timer -= 1


# =========================
# Puzzle Base
# =========================
class Puzzle:
    def __init__(self, name, prompt, solution, hints):
        self.name = name
        self.prompt = prompt
        self.solution = solution
        self.hints = hints
        self.active = False
        self.input_text = ""
        self.solved = False
        self.feedback = ""

    def get_hint(self, level_index):
        if level_index < len(self.hints):
            return self.hints[level_index]
        return None

    def handle_text(self, event):
        if event.key == pygame.K_BACKSPACE:
            self.input_text = self.input_text[:-1]
        elif event.key == pygame.K_RETURN:
            return "submit"
        else:
            self.input_text += event.unicode
        return None


# =========================
# Room with 360 Views
# =========================
class Room:
    def __init__(self, name, difficulty, puzzles_per_room):
        self.name = name
        self.difficulty = difficulty
        self.direction_index = 0  # 0=Front, 1=Right, 2=Back, 3=Left
        self.directions = ["Front", "Right", "Back", "Left"]
        self.puzzles = puzzles_per_room
        self.completed = False
        self.popup_timer = 0
        self.transition_timer = 0
        self.view_slide = 0

        # Interactive objects per direction (rects)
        self.objects = {
            "Front": [
                {"name": "Computer", "rect": pygame.Rect(520, 250, 200, 120), "puzzle": 0},
                {"name": "Sticky Note", "rect": pygame.Rect(200, 300, 100, 60), "puzzle": None},
            ],
            "Right": [
                {"name": "Terminal", "rect": pygame.Rect(540, 260, 180, 120), "puzzle": 1},
                {"name": "Drawer", "rect": pygame.Rect(220, 420, 140, 80), "puzzle": None},
            ],
            "Back": [
                {"name": "Email Board", "rect": pygame.Rect(160, 240, 260, 140), "puzzle": 2},
            ],
            "Left": [
                {"name": "Door", "rect": pygame.Rect(760, 220, 100, 200), "puzzle": None},
                {"name": "Console", "rect": pygame.Rect(140, 260, 200, 120), "puzzle": 3},
            ],
        }

    def all_solved(self):
        return all(p.solved for p in self.puzzles)

    def rotate(self, direction):
        if direction == "left":
            self.direction_index = (self.direction_index - 1) % 4
        elif direction == "right":
            self.direction_index = (self.direction_index + 1) % 4
        self.view_slide = 30

    def current_direction(self):
        return self.directions[self.direction_index]

    def handle_event(self, event, game):
        if event.type == pygame.MOUSEBUTTONDOWN:
            mouse_rect = pygame.Rect(event.pos[0], event.pos[1], 1, 1)
            for obj in self.objects[self.current_direction()]:
                if obj["rect"].colliderect(mouse_rect):
                    if obj["puzzle"] is not None and obj["puzzle"] < len(self.puzzles):
                        self.puzzles[obj["puzzle"]].active = True
                        game.play_click()
                    if obj["name"] == "Door" and self.all_solved():
                        self.completed = True
                        self.popup_timer = 120
                        game.play_success()

        for puzzle in self.puzzles:
            if puzzle.active and event.type == pygame.KEYDOWN:
                action = puzzle.handle_text(event)
                if action == "submit":
                    if puzzle.input_text.strip().lower() in puzzle.solution:
                        puzzle.solved = True
                        puzzle.feedback = "Solved."
                        game.correct += 1
                        game.play_success()
                    else:
                        puzzle.feedback = "Incorrect."
                        game.play_wrong()

    def draw_room_shell(self, surface, wall_color, floor_color):
        surface.fill(wall_color)
        floor_rect = pygame.Rect(0, 380, 900, 220)
        pygame.draw.rect(surface, floor_color, floor_rect)
        pygame.draw.line(surface, (20, 20, 20), (0, 380), (900, 380), 4)
        vignette = pygame.Surface((900, 600), pygame.SRCALPHA)
        pygame.draw.rect(vignette, (0, 0, 0, 120), (0, 0, 900, 600))
        pygame.draw.rect(vignette, (0, 0, 0, 0), (40, 40, 820, 520), border_radius=24)
        surface.blit(vignette, (0, 0))

    def draw_objects(self, surface, font):
        direction = self.current_direction()
        for obj in self.objects[direction]:
            rect = obj["rect"]
            pygame.draw.rect(surface, (70, 70, 90), rect, border_radius=6)
            pygame.draw.rect(surface, (120, 120, 140), rect, 2, border_radius=6)
            label = font.render(obj["name"], True, (230, 230, 230))
            surface.blit(label, (rect.x + 8, rect.y + 8))

    def draw(self, surface, title_font, body_font):
        self.draw_room_shell(surface, (32, 34, 42), (22, 24, 30))
        title = title_font.render(f"{self.name} - {self.current_direction()}", True, (235, 235, 235))
        surface.blit(title, (20, 140))
        self.draw_objects(surface, body_font)

        if self.view_slide > 0:
            slide_overlay = pygame.Surface((900, 600), pygame.SRCALPHA)
            slide_overlay.fill((0, 0, 0, 80))
            surface.blit(slide_overlay, (0, 0))
            self.view_slide -= 1

        for puzzle in self.puzzles:
            if puzzle.active and not puzzle.solved:
                pygame.draw.rect(surface, (10, 10, 10), (160, 200, 580, 230))
                pygame.draw.rect(surface, (100, 100, 100), (160, 200, 580, 230), 2)
                prompt = body_font.render(puzzle.prompt, True, (230, 230, 230))
                surface.blit(prompt, (180, 230))
                text = body_font.render(puzzle.input_text, True, (80, 230, 150))
                surface.blit(text, (180, 270))
                feedback = body_font.render(puzzle.feedback, True, (240, 200, 80))
                surface.blit(feedback, (180, 310))


# =========================
# Home Page (Main Menu)
# =========================
class HomePage:
    def __init__(self, title_font, body_font):
        self.title_font = title_font
        self.body_font = body_font
        self.diff_buttons = {
            "Easy": pygame.Rect(80, 160, 140, 40),
            "Medium": pygame.Rect(240, 160, 140, 40),
            "Hard": pygame.Rect(400, 160, 140, 40),
        }
        self.view_badges_button = pygame.Rect(680, 500, 180, 40)

    def build_level_grid(self, level_count):
        columns = 5
        grid = []
        start_x = 60
        start_y = 240
        cell_w = 96
        cell_h = 40
        gap_x = 18
        gap_y = 16
        for i in range(level_count):
            col = i % columns
            row = i // columns
            x = start_x + col * (cell_w + gap_x)
            y = start_y + row * (cell_h + gap_y)
            grid.append(pygame.Rect(x, y, cell_w, cell_h))
        return grid

    def handle_event(self, event, game):
        if event.type != pygame.MOUSEBUTTONDOWN:
            return
        mouse_rect = pygame.Rect(event.pos[0], event.pos[1], 1, 1)

        for diff, rect in self.diff_buttons.items():
            if rect.colliderect(mouse_rect):
                game.current_difficulty = diff
                game.current_level_index = 0
                game.play_click()
                return

        level_count = game.level_manager.level_counts[game.current_difficulty]
        level_grid = self.build_level_grid(level_count)
        for i in range(level_count):
            rect = level_grid[i]
            if rect.colliderect(mouse_rect):
                if game.level_manager.is_unlocked(game.current_difficulty, i):
                    game.current_level_index = i
                    game.start_level()
                    game.play_click()
                return

        if self.view_badges_button.colliderect(mouse_rect):
            game.show_badges = not game.show_badges
            game.play_click()

    def draw(self, surface, game):
        surface.fill((18, 18, 26))
        for x in range(0, 900, 40):
            pygame.draw.line(surface, (28, 28, 36), (x, 0), (x, 600))
        for y in range(0, 600, 40):
            pygame.draw.line(surface, (28, 28, 36), (0, y), (900, y))

        title = self.title_font.render("CyberLock Quest - Home", True, (230, 230, 230))
        surface.blit(title, (60, 80))

        diff_label = self.body_font.render(f"Difficulty: {game.current_difficulty}", True, (200, 200, 200))
        surface.blit(diff_label, (60, 130))

        for diff, rect in self.diff_buttons.items():
            color = (70, 90, 120) if diff == game.current_difficulty else (40, 40, 60)
            pygame.draw.rect(surface, color, rect, border_radius=6)
            pygame.draw.rect(surface, (120, 120, 150), rect, 2, border_radius=6)
            label = self.body_font.render(diff, True, (230, 230, 230))
            surface.blit(label, (rect.x + 20, rect.y + 10))

        level_count = game.level_manager.level_counts[game.current_difficulty]
        level_grid = self.build_level_grid(level_count)
        for i in range(level_count):
            rect = level_grid[i]
            unlocked = game.level_manager.is_unlocked(game.current_difficulty, i)
            color = (60, 60, 80) if unlocked else (30, 30, 40)
            pygame.draw.rect(surface, color, rect, border_radius=6)
            pygame.draw.rect(surface, (100, 100, 120), rect, 2, border_radius=6)
            label = self.body_font.render(str(i + 1), True, (230, 230, 230))
            surface.blit(label, (rect.x + 30, rect.y + 10))

        stats = [
            f"Levels Completed: {game.level_manager.data['stats']['levels_completed']}",
            f"Badges: {len(game.level_manager.data['stats']['badges'])}",
            f"Accuracy: {game.correct}",
            f"Hints Used: {game.hints_used}",
        ]
        for i, line in enumerate(stats):
            text = self.body_font.render(line, True, (210, 210, 210))
            surface.blit(text, (640, 220 + i * 26))

        pygame.draw.rect(surface, (50, 50, 60), self.view_badges_button, border_radius=6)
        pygame.draw.rect(surface, (120, 120, 140), self.view_badges_button, 2, border_radius=6)
        badge_text = self.body_font.render("View Badges", True, (230, 230, 230))
        surface.blit(badge_text, (self.view_badges_button.x + 16, self.view_badges_button.y + 8))

        if game.show_badges:
            pygame.draw.rect(surface, (10, 10, 10), (620, 120, 260, 260))
            pygame.draw.rect(surface, (150, 150, 150), (620, 120, 260, 260), 2)
            header = self.body_font.render("Badges", True, (230, 230, 230))
            surface.blit(header, (640, 140))
            badges = game.level_manager.data["stats"]["badges"]
            for i, badge in enumerate(badges[:8]):
                label = self.body_font.render(f"- {badge}", True, (220, 220, 220))
                surface.blit(label, (640, 170 + i * 24))


# =========================
# Game
# =========================
class Game:
    def __init__(self):
        pygame.init()
        pygame.font.init()
        self.audio_enabled = True
        try:
            pygame.mixer.init()
        except Exception:
            self.audio_enabled = False

        self.screen = pygame.display.set_mode((900, 600))
        pygame.display.set_caption("CyberLock Quest")
        self.clock = pygame.time.Clock()

        self.title_font = pygame.font.SysFont("consolas", 28)
        self.body_font = pygame.font.SysFont("consolas", 20)

        # Sounds (fallback to tones)
        if self.audio_enabled:
            self.click_sound = make_tone_sound(520, 80, 0.2)
            self.success_sound = make_tone_sound(880, 120, 0.3)
            self.wrong_sound = make_tone_sound(220, 140, 0.3)
            self.unlock_sound = make_tone_sound(660, 150, 0.3)
        else:
            self.click_sound = None
            self.success_sound = None
            self.wrong_sound = None
            self.unlock_sound = None

        self.level_manager = LevelManager()
        self.current_difficulty = "Easy"
        self.current_level_index = 0
        self.correct = self.level_manager.data["stats"]["correct"]
        self.hints_used = self.level_manager.data["stats"]["hints_used"]
        self.show_badges = False

        self.hud = HUD(self.body_font)
        self.inventory = Inventory(self.body_font)
        self.hint_system = HintSystem(self.body_font)
        self.hint_button = pygame.Rect(760, 10, 120, 36)

        self.home_page = HomePage(self.title_font, self.body_font)
        self.active_room = None

        self.time_limit_seconds = 45 * 60
        self.start_ticks = pygame.time.get_ticks()
        self.page = "home"

    def play_click(self):
        if self.click_sound:
            self.click_sound.play()

    def play_success(self):
        if self.success_sound:
            self.success_sound.play()

    def play_wrong(self):
        if self.wrong_sound:
            self.wrong_sound.play()

    def play_unlock(self):
        if self.unlock_sound:
            self.unlock_sound.play()

    def use_hint_penalty(self):
        self.hints_used += 1
        self.time_limit_seconds = max(0, self.time_limit_seconds - 30)
        self.level_manager.data["stats"]["hints_used"] = self.hints_used
        self.level_manager.save()

    def get_time_left(self):
        elapsed = (pygame.time.get_ticks() - self.start_ticks) // 1000
        remaining = max(0, self.time_limit_seconds - elapsed)
        return remaining

    def start_level(self):
        if not self.level_manager.is_unlocked(self.current_difficulty, self.current_level_index):
            return
        self.time_limit_seconds = 45 * 60
        self.start_ticks = pygame.time.get_ticks()
        self.inventory.clear()
        self.hint_system.reset()
        self.active_room = self.build_room()
        self.page = "room"

    def build_room(self):
        difficulty = self.current_difficulty
        if difficulty == "Easy":
            puzzles = [
                Puzzle("Password", "Decode: 'sdvvzrug' (Caesar +3)", ["password"], ["Shift back by 3.", "It's a common word.", "Type 'password'."]),
                Puzzle("Phishing", "Identify phishing keyword:", ["verify", "urgent"], ["Look for urgency.", "Request to verify.", "Type 'verify'."]),
            ]
        elif difficulty == "Medium":
            puzzles = [
                Puzzle("Password", "Unscramble: 'p@55w0rd!23'", ["p@55w0rd!23"], ["No trick here.", "Type exactly.", "p@55w0rd!23"]),
                Puzzle("Network", "Keyword indicating attack:", ["brute", "privilege"], ["Search alerts.", "Look for attack terms.", "Type 'brute'."]),
                Puzzle("Phishing", "Phishing indicator:", ["login", "reset"], ["Look for reset words.", "Check login language.", "Type 'reset'."]),
            ]
        else:
            puzzles = [
                Puzzle("Password", "Layered cipher: use hidden clue", ["secure#2026"], ["Check other views.", "Sticky note has clue.", "Type secure#2026"]),
                Puzzle("Network", "High-risk keyword:", ["rootkit", "credential"], ["Look for severe alerts.", "Search rootkit line.", "Type rootkit"]),
                Puzzle("Social", "Safest response keyword:", ["verify"], ["Verify first.", "Don't share info.", "Type verify"]),
                Puzzle("Phishing", "Decoy-heavy indicator:", ["spoof", "impersonation"], ["Sender spoofing.", "Impersonation clue.", "Type spoof"]),
            ]

        return Room("Cyber Room", difficulty, puzzles)

    def finish_level(self):
        self.level_manager.complete_level(self.current_difficulty, self.current_level_index)
        if self.active_room and self.active_room.all_solved():
            if self.hints_used == 0:
                self.level_manager.add_badge("No-Hint Win")
            if self.correct >= 3:
                self.level_manager.add_badge("High Accuracy")
        self.active_room = None
        self.page = "home"
        self.play_unlock()

    def handle_rotation(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_LEFT:
                self.active_room.rotate("left")
            elif event.key == pygame.K_RIGHT:
                self.active_room.rotate("right")

    def run(self):
        running = True
        while running:
            self.clock.tick(60)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                if self.page == "home":
                    self.home_page.handle_event(event, self)
                elif self.page == "room" and self.active_room:
                    self.handle_rotation(event)
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        mouse_rect = pygame.Rect(event.pos[0], event.pos[1], 1, 1)
                        if self.hint_button.colliderect(mouse_rect):
                            for puzzle in self.active_room.puzzles:
                                if puzzle.active and not puzzle.solved:
                                    self.hint_system.request_hint(puzzle, self)
                                    self.play_click()
                    self.active_room.handle_event(event, self)

            if self.page == "room" and self.active_room:
                time_left = self.get_time_left()
                if time_left <= 0:
                    self.page = "home"
                    self.active_room = None

                if self.active_room.completed:
                    self.active_room.transition_timer += 1
                    if self.active_room.transition_timer > 60:
                        self.finish_level()

                minutes = time_left // 60
                seconds = time_left % 60
                state = {
                    "difficulty": self.current_difficulty,
                    "level": self.current_level_index + 1,
                    "time_left_mmss": f"{minutes:02d}:{seconds:02d}",
                    "correct": self.correct,
                    "hints_used": self.hints_used,
                }

                self.active_room.draw(self.screen, self.title_font, self.body_font)
                self.hud.draw(self.screen, state)

                pygame.draw.rect(self.screen, (50, 50, 50), self.hint_button, border_radius=6)
                pygame.draw.rect(self.screen, (120, 120, 120), self.hint_button, 2, border_radius=6)
                hint_label = self.body_font.render("Hint", True, (230, 230, 230))
                self.screen.blit(hint_label, (self.hint_button.x + 34, self.hint_button.y + 8))

                self.inventory.draw(self.screen)
                self.hint_system.draw(self.screen)

                if self.active_room.popup_timer > 0:
                    pygame.draw.rect(self.screen, (0, 0, 0), (300, 240, 300, 80))
                    pygame.draw.rect(self.screen, (200, 200, 200), (300, 240, 300, 80), 2)
                    msg = self.body_font.render("Level Complete!", True, (220, 220, 220))
                    self.screen.blit(msg, (340, 270))
                    self.active_room.popup_timer -= 1

            elif self.page == "home":
                self.home_page.draw(self.screen, self)

            pygame.display.flip()

        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    Game().run()
