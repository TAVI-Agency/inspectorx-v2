/**
 * Все строки UI. Единственный источник текста интерфейса.
 * Позже добавим uz.ts / en.ts с тем же контрактом.
 */

export const ru = {
  common: {
    appName: 'InspectorX',
    tagline: 'Чек-лист соответствия вашего бизнеса',
    loading: 'Загружаем…',
    error: 'Не получилось загрузить данные. Обновите страницу.',
    retry: 'Повторить',
    close: 'Закрыть',
    back: 'Назад',
    send: 'Отправить',
    sending: 'Отправляем…',
    save: 'Сохранить',
    cancel: 'Отмена',
    signIn: 'Войти',
    signOut: 'Выйти',
    register: 'Регистрация',
    cabinet: 'Кабинет',
    pricing: 'Тариф',
    verified: 'проверено',
    updated: 'обновлено',
  },

  header: {
    monitoring: (acts: string) => `${acts} на мониторинге`,
    updated: (time: string) => `обновлено ${time}`,
    weekly: (changes: string) => `${changes} за неделю`,
    actsUnit: ['акт', 'акта', 'актов'] as const,
    changesUnit: ['изменение', 'изменения', 'изменений'] as const,
    themeToggle: 'Переключить тему',
    menu: 'Меню',
  },

  footer: {
    contacts: 'Контакты',
    email: 'hello@inspectorx.uz',
    telegram: 'Telegram: @inspectorx_uz',
    legal: 'Оферта · Политика конфиденциальности — скоро',
    disclaimer:
      'InspectorX — информационный сервис, не юридическая консультация.',
    rights: '© 2026 InspectorX',
  },

  landing: {
    heroTitle: 'Все требования закона к вашему товару. На одной странице.',
    heroSubtitle:
      'Что делать, к какому сроку, какими документами — и что будет, если не сделать.',
    searchPlaceholder: 'Товар или код ТН ВЭД…',
    searchPlaceholderService: 'Услуга или код ИКПУ…',
    searchPlaceholderShort: 'Товар или код…',
    searchPlaceholderServiceShort: 'Услуга или код…',
    kindProduct: 'Товар',
    kindService: 'Услуга',
    examplesLabel: 'Посмотрите на примере:',
    howTitle: 'Как это работает',
    howSteps: [
      {
        title: 'Найдите свой товар',
        text: 'По названию, коду ТН ВЭД или ИКПУ. Подсказки сверят код за вас.',
      },
      {
        title: 'Получите чек-лист требований',
        text: 'Каждое требование: что делать, документы, сроки, санкции — со ссылкой на пункт закона.',
      },
      {
        title: 'Следите за изменениями',
        text: 'Закон поменялся — вы узнаете первым: что именно изменилось и что теперь делать.',
      },
    ],
    searchEmptyTitle: 'Ничего не нашли по запросу',
    searchEmptyText:
      'Оставьте заявку — наполним ваш товар в первую очередь и напишем вам.',
    searchEmptyCta: 'Оставить заявку',
    searchEmptyDone: 'Заявка принята. Напишем, когда наполним.',
    suggestOfficial: 'Официальное название кода',
  },

  product: {
    checkedStamp: (date: string) => `Проверено ${date}`,
    complexity: (n: number) => `Сложность ${n}/10`,
    complexityLabel: 'индекс сложности',
    codesLabel: 'Коды',
    hsLabel: 'ТН ВЭД',
    ikpuLabel: 'ИКПУ',
    categoryLabel: 'Категория',
    officialNameLabel: 'Официальное название кода',
    followCta: 'Следить за товаром',
    followedCta: 'В вашем портфеле',
    metrics: {
      requirements: 'Требований',
      documents: 'Документов собрать',
      maxSanction: 'Макс. санкция',
      changes30d: 'Изменений за 30 дней',
    },
    stagesAll: 'Все этапы',
    listTitle: 'Требования',
    quiet30d: 'За 30 дней — тишина. Это хорошие новости.',
    noRequirementsTitle: 'По этому товару требования ещё не наполнены',
    noRequirementsText:
      'Оставьте заявку — наполним и сообщим. Это бесплатно.',
    notifyWhenReady: 'Уведомить, когда готово',
    notifyDone: 'Заявка принята. Сообщим, когда наполним.',
  },

  requirement: {
    deontic: {
      obligation: 'обязанность',
      prohibition: 'запрет',
      permission: 'льгота',
    },
    roles: {
      producer: 'производитель',
      importer: 'импортёр',
      exporter: 'экспортёр',
      seller: 'продавец',
      carrier: 'перевозчик',
      all: 'для всех',
    },
    operations: {
      product: 'товар',
      realization: 'реализация',
      import: 'импорт',
      export: 'экспорт',
      transit: 'транзит',
      re_export: 'реэкспорт',
      re_import: 'реимпорт',
    },
    status: {
      active: 'действует',
      changed: (date: string) => `изменилось ${date}`,
      upcoming: (date: string) => `изменится с ${date}`,
    },
    underReview: 'проверяется обновление',
    trust: {
      ai_draft: 'AI-черновик',
      lawyer_verified: (date: string) => `Проверено юристом ${date}`,
      official_answer: 'Официальный ответ',
    },
    card: {
      description: 'Суть требования',
      howTo: 'Как исполнить',
      term: 'Срок',
      cost: 'Стоимость',
      documents: 'Документы',
      whereToGet: 'Где взять',
      authority: 'Ведомство',
      sanctions: 'Санкции',
      sanctionArticle: 'Статья',
      faq: 'Вопросы по требованию',
      askQuestion: 'Задать вопрос',
      grRequest: 'Официальный запрос (GR)',
      history: 'История изменений',
      historyCount: (n: number) => `История изменений (${n})`,
      was: 'Было',
      now: 'Стало',
      source: 'Источник',
      sourceAct: 'Акт',
      sourceParagraph: 'Пункт',
      sourceRevision: 'Редакция',
      openAct: 'Открыть акт',
      verbatimLabel: 'Точная цитата',
      verbatimOriginal: 'Оригинал (UZ)',
      verbatimTranslation: 'Перевод (RU)',
      legalPanelTitle: 'Юридический слой',
    },
  },

  paywall: {
    locked: 'Доступно по подписке',
    lockedText:
      'Шаги исполнения, документы, суммы санкций и точные цитаты закона — в раннем доступе.',
    cta: 'Открыть доступ',
    teaserNote: 'Бесплатно: список требований, типы, ведомства и источники.',
  },

  pricing: {
    title: 'Ранний доступ',
    subtitle:
      'Полный чек-лист по вашим товарам и первые уведомления об изменениях — раньше всех.',
    per: 'в месяц за компанию',
    benefits: [
      'Полные карточки требований: шаги, документы, сроки, санкции с суммами',
      'Точные цитаты закона с реквизитами пункта и редакции',
      'Лента изменений по вашим товарам: было/стало и что делать',
      'Уведомления: email-дайджест и Telegram',
      'Вопросы юристу по требованиям — приоритетный разбор',
      'Влияние на очередь наполнения: ваши товары — первыми',
    ],
    formTitle: 'Оставить заявку',
    formSubtitle: 'Свяжемся в течение рабочего дня и включим доступ.',
    nameLabel: 'Имя',
    namePlaceholder: 'Как к вам обращаться',
    contactLabel: 'Телефон или Telegram',
    contactPlaceholder: '+998 __ ___ __ __ или @username',
    companyLabel: 'Компания',
    companyPlaceholder: 'Название компании (необязательно)',
    submit: 'Отправить заявку',
    thanksTitle: 'Спасибо! Заявка принята.',
    thanksText:
      'Свяжемся в течение рабочего дня, включим ранний доступ и поможем настроить портфель товаров.',
    thanksCta: 'Вернуться к товарам',
    validation: {
      nameRequired: 'Укажите имя',
      contactRequired: 'Укажите телефон или Telegram',
    },
  },

  cabinet: {
    title: 'Мои товары',
    weekSummary: (changes: string, actions: number, date: string) =>
      actions > 0
        ? `За неделю: ${changes} · ${actions} требуют действий до ${date}`
        : `За неделю: ${changes}`,
    portfolioEmpty: {
      title: 'В портфеле пока пусто',
      text: 'Найдите товар и нажмите «Следить» — изменения по нему будут приходить сюда.',
      cta: 'Найти товар',
    },
    productStatus: {
      deadline: (date: string) => `дедлайн ${date}`,
      noAction: 'действий не требуется',
      quiet: 'без изменений 30 дней',
    },
    unreadShort: (n: number) => `${n} новых`,
    feedTitle: 'Лента изменений',
    importance: { high: 'важно', medium: 'средняя', low: 'низкая' },
    effectiveIn: (days: number, date: string) =>
      `вступает ${date} — ${days === 0 ? 'сегодня' : `осталось ${days} дн.`}`,
    effectiveAlready: 'уже действует',
    whatToDo: 'Что делать',
    inFavor: 'Изменение в вашу пользу',
    nothingToDo: 'ничего — изменение в вашу пользу',
    toRequirement: 'К требованию',
    markRead: 'Отметить прочитанным',
    draftNpa: 'проект НПА · обсуждается',
    draftNpaLink: 'Общественное обсуждение',
    digestTitle: 'Дайджест изменений',
    digestText: 'Как присылать изменения по вашим товарам:',
    digestEmail: 'Email еженедельно',
    digestTelegram: 'Telegram мгновенно',
    digestSaved: 'Настройки дайджеста сохранены',
    feedQuiet: 'За 30 дней тишина. Это хорошие новости.',
  },

  auth: {
    loginTitle: 'Вход',
    registerTitle: 'Регистрация',
    email: 'Email',
    password: 'Пароль',
    fullName: 'Имя',
    fullNamePlaceholder: 'Имя и фамилия',
    loginCta: 'Войти',
    registerCta: 'Создать аккаунт',
    switchToRegister: 'Нет аккаунта? Зарегистрируйтесь',
    switchToLogin: 'Уже есть аккаунт? Войдите',
    loginRequired: 'Войдите, чтобы следить за товарами',
    errors: {
      invalid: 'Неверный email или пароль',
      exists: 'Такой аккаунт уже есть — попробуйте войти',
      weakPassword: 'Пароль должен быть не короче 6 символов',
      notConfirmed: 'Email не подтверждён — проверьте почту и перейдите по ссылке',
      generic: 'Не получилось. Проверьте данные и попробуйте ещё раз.',
    },
  },

  dev: {
    menuTitle: 'Демо-режим',
    mockSubscriber: 'Я подписчик (мок)',
    mockSubscriberHint:
      'Показывает полный вид карточек. Данные details у реальных требований — демо-шаблон до входа под реальной подпиской.',
  },
} as const

export type Dict = typeof ru
