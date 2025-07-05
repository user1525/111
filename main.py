package main

import (
	"bufio"
	"database/sql"
	"log"
	"os"
	"strings"
	"time"

	tgbotapi "github.com/go-telegram-bot-api/telegram-bot-api/v5"
)

// --- Структуры ---

type UserProfile struct {
	UserID     int64
	Username   string
	Department string
	Profession string
	City       string
	Experience string
	Portfolio  string
}

var (
	bot          *tgbotapi.BotAPI
	db           *sql.DB
	userStates   = map[int64]string{}       // состояние пользователя (ввод данных)
	userTempData = map[int64]*UserProfile{} // временный профиль при создании
)

// --- Цеха и профессии ---

var departments = map[string][]string{
	"Режиссерский цех": {
		"Режиссеры-постановщики",
		"Режиссеры анимации",
		"Вторые режиссеры",
		"Ассистенты второго режиссера",
		"Ассистенты режиссера по актерам",
		"Помощники режиссера",
		"Бригадиры АМС",
		"Кастинг-директора",
	},
	"Звуковой цех": {
		"Звукорежиссеры",
		"Ассистенты звукорежиссера",
	},
	"Операторский цех": {
		"Вторые операторы",
		"Камермены",
		"Фокус-пуллеры",
		"Операторы и пилоты коптеров",
		"Гаффер",
		"Осветители",
		"Грип",
	},
	"Каскадерско-пиротехнический департамент": {
		"Постановщики трюков",
		"Каскадеры",
		"Пиротехники",
	},
	// Добавьте остальные цеха и профессии по аналогии
}

// --- Чтение токена из конфига ---

func readTokenFromConfig(filename string) (string, error) {
	f, err := os.Open(filename)
	if err != nil {
		return "", err
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if strings.HasPrefix(line, "TOKEN=") {
			return strings.TrimSpace(strings.TrimPrefix(line, "TOKEN=")), nil
		}
	}
	return "", nil
}

// --- Инициализация базы данных ---

func initDB() error {
	var err error
	db, err = sql.Open("sqlite", "profiles.db")
	if err != nil {
		return err
	}
	_, err = db.Exec(`CREATE TABLE IF NOT EXISTS users(
		user_id INTEGER PRIMARY KEY,
		username TEXT,
		department TEXT,
		profession TEXT,
		city TEXT,
		experience TEXT,
		portfolio TEXT
	)`)
	return err
}

// --- Сохранение профиля в БД ---

func saveUserProfile(userID int64, username string) error {
	p := userTempData[userID]
	if p == nil {
		return nil
	}

	_, err := db.Exec(`
		INSERT INTO users(user_id, username, department, profession, city, experience, portfolio)
		VALUES (?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT(user_id) DO UPDATE SET
		username=excluded.username,
		department=excluded.department,
		profession=excluded.profession,
		city=excluded.city,
		experience=excluded.experience,
		portfolio=excluded.portfolio
	`, p.UserID, username, p.Department, p.Profession, p.City, p.Experience, p.Portfolio)

	return err
}

// --- Удаление сообщения через delay секунд ---

func deleteMessageLater(chatID int64, messageID int, delaySeconds int) {
	go func() {
		time.Sleep(time.Duration(delaySeconds) * time.Second)
		bot.Request(tgbotapi.NewDeleteMessage(chatID, messageID))
	}()
}

// --- Отправка сообщения с автоудалением через 3 минуты ---

func sendMessageAutoDelete(chatID int64, text string, replyMarkup interface{}) (tgbotapi.Message, error) {
	msg := tgbotapi.NewMessage(chatID, text)
	if replyMarkup != nil {
		msg.ReplyMarkup = replyMarkup
	}
	sent, err := bot.Send(msg)
	if err == nil {
		deleteMessageLater(chatID, sent.MessageID, 180)
	}
	return sent, err
}

// --- Построение меню выбора цеха ---

func buildDepartmentsKeyboard() tgbotapi.InlineKeyboardMarkup {
	var buttons []tgbotapi.InlineKeyboardButton
	for dept := range departments {
		buttons = append(buttons, tgbotapi.NewInlineKeyboardButtonData(dept, "dept_"+dept))
	}
	keyboard := tgbotapi.NewInlineKeyboardMarkup(
		tgbotapi.NewInlineKeyboardRow(buttons...),
	)
	return keyboard
}

// --- Построение меню выбора профессии для цеха ---

func buildProfessionsKeyboard(department string) tgbotapi.InlineKeyboardMarkup {
	profs, ok := departments[department]
	if !ok {
		return tgbotapi.InlineKeyboardMarkup{}
	}
	var rows [][]tgbotapi.InlineKeyboardButton
	row := []tgbotapi.InlineKeyboardButton{}
	for i, prof := range profs {
		row = append(row, tgbotapi.NewInlineKeyboardButtonData(prof, "prof_"+prof))
		if (i+1)%2 == 0 {
			rows = append(rows, row)
			row = []tgbotapi.InlineKeyboardButton{}
		}
	}
	if len(row) > 0 {
		rows = append(rows, row)
	}
	// Кнопка назад
	backBtn := tgbotapi.NewInlineKeyboardButtonData("⬅ Назад", "back_dept")
	rows = append(rows, tgbotapi.NewInlineKeyboardRow(backBtn))
	return tgbotapi.NewInlineKeyboardMarkup(rows...)
}

// --- Обработка callbackQuery ---

func handleCallbackQuery(callback *tgbotapi.CallbackQuery) {
	userID := callback.From.ID
	data := callback.Data

	switch {
	case data == "create_profile":
		userStates[userID] = "input_department"
		userTempData[userID] = &UserProfile{UserID: userID}
		msg, _ := sendMessageAutoDelete(callback.Message.Chat.ID, "Выберите ваш цех:", buildDepartmentsKeyboard())
		deleteMessageLater(callback.Message.Chat.ID, callback.Message.MessageID, 1)
		bot.Request(tgbotapi.NewAnswerCallbackQuery(callback.ID, "Создание анкеты"))
	case strings.HasPrefix(data, "dept_"):
		department := strings.TrimPrefix(data, "dept_")
		userTempData[userID].Department = department
		userStates[userID] = "input_profession"
		msg, _ := sendMessageAutoDelete(callback.Message.Chat.ID, "Выберите профессию в цехе "+department+":", buildProfessionsKeyboard(department))
		deleteMessageLater(callback.Message.Chat.ID, callback.Message.MessageID, 1)
		bot.Request(tgbotapi.NewAnswerCallbackQuery(callback.ID, "Выбран цех "+department))
	case strings.HasPrefix(data, "prof_"):
		profession := strings.TrimPrefix(data, "prof_")
		userTempData[userID].Profession = profession
		userStates[userID] = "input_city"
		sendMessageAutoDelete(callback.Message.Chat.ID, "Введите ваш город проживания:", nil)
		deleteMessageLater(callback.Message.Chat.ID, callback.Message.MessageID, 1)
		bot.Request(tgbotapi.NewAnswerCallbackQuery(callback.ID, "Выбрана профессия "+profession))
	case data == "back_dept":
		userStates[userID] = "input_department"
		msg, _ := sendMessageAutoDelete(callback.Message.Chat.ID, "Выберите ваш цех:", buildDepartmentsKeyboard())
		deleteMessageLater(callback.Message.Chat.ID, callback.Message.MessageID, 1)
		bot.Request(tgbotapi.NewAnswerCallbackQuery(callback.ID, "Назад к цехам"))
	case data == "view_profiles":
		showProfilesList(callback.Message.Chat.ID)
		deleteMessageLater(callback.Message.Chat.ID, callback.Message.MessageID, 1)
		bot.Request(tgbotapi.NewAnswerCallbackQuery(callback.ID, "Список анкет"))
	default:
		bot.Request(tgbotapi.NewAnswerCallbackQuery(callback.ID, "Неизвестная команда"))
	}
}

// --- Отображение списка профилей (простой вывод) ---

func showProfilesList(chatID int64) {
	rows, err := db.Query("SELECT username, department, profession, city FROM users")
	if err != nil {
		sendMessageAutoDelete(chatID, "Ошибка при запросе профилей", nil)
		return
	}
	defer rows.Close()

	var result strings.Builder
	result.WriteString("📋 Список анкет:\n\n")
	for rows.Next() {
		var username, department, profession, city string
		rows.Scan(&username, &department, &profession, &city)
		result.WriteString("👤 @" + username + "\n")
		result.WriteString("Цех: " + department + "\n")
		result.WriteString("Профессия: " + profession + "\n")
		result.WriteString("Город: " + city + "\n\n")
	}
	if result.Len() == 0 {
		result.WriteString("Профили не найдены.")
	}

	sendMessageAutoDelete(chatID, result.String(), nil)
}

// --- Обработка текстовых сообщений ---

func handleMessage(msg *tgbotapi.Message) {
	userID := msg.From.ID
	state := userStates[userID]

	switch state {
	case "input_city":
		text := strings.TrimSpace(msg.Text)
		if text == "" {
			sendMessageAutoDelete(msg.Chat.ID, "Город не может быть пустым. Введите снова:", nil)
			return
		}
		setUserTempField(userID, "city", text)
		userStates[userID] = "input_experience"
		sendMessageAutoDelete(msg.Chat.ID, "Введите ваш опыт работы (коротко):", nil)
		deleteMessageLater(msg.Chat.ID, msg.MessageID, 5)

	case "input_experience":
		text := strings.TrimSpace(msg.Text)
		if text == "" {
			sendMessageAutoDelete(msg.Chat.ID, "Опыт работы не может быть пустым. Введите снова:", nil)
			return
		}
		setUserTempField(userID, "experience", text)
		userStates[userID] = "input_portfolio"
		sendMessageAutoDelete(msg.Chat.ID, "Введите ссылку на портфолио или краткое описание:", nil)
		deleteMessageLater(msg.Chat.ID, msg.MessageID, 5)

	case "input_portfolio":
		text := strings.TrimSpace(msg.Text)
		if text == "" {
			sendMessageAutoDelete(msg.Chat.ID, "Портфолио не может быть пустым. Введите снова:", nil)
			return
		}
		setUserTempField(userID, "portfolio", text)

		err := saveUserProfile(userID, msg.From.UserName)
		if err != nil {
			sendMessageAutoDelete(msg.Chat.ID, "Ошибка при сохранении анкеты.", nil)
			log.Println("Save profile error:", err)
			return
		}
		sendMessageAutoDelete(msg.Chat.ID, "Анкета успешно сохранена!", nil)
		userStates[userID] = ""
		userTempData[userID] = nil
		deleteMessageLater(msg.Chat.ID, msg.MessageID, 5)

	default:
		// Основное меню
		keyboard := tgbotapi.NewInlineKeyboardMarkup(
			tgbotapi.NewInlineKeyboardRow(
				tgbotapi.NewInlineKeyboardButtonData("Создать анкету", "create_profile"),
				tgbotapi.NewInlineKeyboardButtonData("Просмотреть анкеты", "view_profiles"),
			),
		)
		sendMessageAutoDelete(msg.Chat.ID, "Привет! Выберите действие:", keyboard)
		deleteMessageLater(msg.Chat.ID, msg.MessageID, 5)
	}
}

func setUserTempField(userID int64, field, value string) {
	p := userTempData[userID]
	if p == nil {
		p = &UserProfile{UserID: userID}
		userTempData[userID] = p
	}
	switch field {
	case "department":
		p.Department = value
	case "profession":
		p.Profession = value
	case "city":
		p.City = value
	case "experience":
		p.Experience = value
	case "portfolio":
		p.Portfolio = value
	}
}

func main() {
	// Читаем токен
	token, err := readTokenFromConfig("config.cfg")
	if err != nil || token == "" {
		log.Fatal("TOKEN not found in config.cfg")
	}

	// Инициализация бота
	bot, err = tgbotapi.NewBotAPI(token)
	if err != nil {
		log.Fatal(err)
	}
	log.Printf("Authorized on account %s", bot.Self.UserName)

	// Инициализация БД
	err = initDB()
	if err != nil {
		log.Fatal("DB init error:", err)
	}

	u := tgbotapi.NewUpdate(0)
	u.Timeout = 30

	updates := bot.GetUpdatesChan(u)

	for update := range updates {
		if update.Message != nil {
			go handleMessage(update.Message)
		} else if update.CallbackQuery != nil {
			go handleCallbackQuery(update.CallbackQuery)
		}
	}
}
