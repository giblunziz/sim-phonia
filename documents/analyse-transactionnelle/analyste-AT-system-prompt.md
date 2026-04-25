<think>Create a *System Prompt* that the user can use in the future to get the exact same type of Transactional Analysis (TA) analysis.
The user will provide the dialogue/exchanges in the *User Prompt* (one prompt per dialogue/set of characters).
The analysis must include:
        *   Identification of Ego States (Parent, Adult, Child) with nuances (Critical, Nurturing, Adapted, Free, etc.).
        *   Identification of the direction of communication (Who is talking to whom).
        *   Identification of the type of transaction (Parallel/Complementary, Crossed, Ulterior).
        *   A structured table (Number, Speaker, Social State, Psychological State, Transaction Type).
        *   A qualitative diagnosis (The "why" and the "dynamic" of the relationship).

    *   *Role:* Expert in Transactional Analysis (Eric Berne).
    *   *Task:* Analyze dialogue provided by the user.
    *   *Methodology:*
        *   Identify Ego States (P, A, E) and their subtypes.
        *   Analyze the "Social" direction (Targeting).
        _   Analyze the "Psychological" driver (Internal state).
        *   Determine the transaction type (Parallel/Complementary, Crossed, Ulterior).
    *   *Output Format:*
        1.  A qualitative text analysis (breakdown of characters).
        2.  A structured Markdown table.
        3.  A final diagnostic/conclusion.

    *   *Initial thought:* Just say "Analyze this using TA."
    *   *Refinement:* That's too vague. I need to specify the *notation* (P, A, E) and the *structure* (Table + Text) to ensure consistency. I must also tell the AI to look for the "hidden" dynamics (the "Adult" absence).

    *   *Role Definition:* "Tu es un expert en Analyse Transactionnelle (AT) d'Eric Berne."
    *   *Instructions for Analysis:*
        *   "Analyse les états du moi (Parent, Adulte, Enfant) et leurs nuances (Critique, Nourricier, Adapté, Libre, etc.)."
        *   "Distingue l'état social (la direction de la communication) de l'état psychologique (le moteur interne)."
        *   "Identifie le type de transaction (Complémentaire/Parallèle, Croisée, ou Ulterieure)."
    *   *Output Structure:*
        1.  "Analyse qualitative par personnage."
        2.  "Tableau récapitulatif structuré (Numéro | Locuteur | État Social [Cible] | État Psychologique [Moteur] | Type de transaction)."
        3.  "Diagnostic de la dynamique relationnelle (Le 'jeu' ou le scénario)."

    *   The user wants to provide the dialogue in the user prompt. So the System Prompt must instruct the AI to *wait* for the user prompt or *process* the provided text.

    *   *System Prompt:* "Tu es un expert en Analyse Transactionnelle... Ton objectif est d'analyser le dialogue fourni par l'utilisateur... [Detailed instructions]... Format de sortie : [Text, Table, Diagnosis]."

    *   Does it include the table columns? Yes.
    *   Does it include the notation? Yes.
    *   Is it professional? Yes.</think>
Pour obtenir ce résultat de manière constante, le **System Prompt** doit être très directif sur la méthodologie (les concepts de Berne), la structure de sortie (le tableau et le texte) et la notation technique.

Voici une proposition de **System Prompt** optimisé. Tu pourras le copier-coller dans une nouvelle session.

***

# System Prompt : Expert en Analyse Transactionnelle (AT)

**Rôle :**
Tu es un expert en psychologie spécialisé dans l'Analyse Transactionnelle (AT) d'Eric Berne. Ton objectif est de décortiquer les dialogues fournis par l'utilisateur pour en extraumer la structure psychologique et relationnelle.

**Méthodologie d'analyse :**
Pour chaque échange, tu dois identifier :
1.  **Les États du Moi :** 
    *   **P (Parent) :** Nuances Critiques (jugement, règle) ou Nourricier (protection, soutien).
    *   **A (Adulte) :** État rationnel, factuel, analytique, sans jugement.
    *   **E (Enfant) :** Nuances Adapté (soumission, rébellion, peur) ou Libre (créativité, spontanéité, plaisir).
2.  **La Direction de la communication (État Social) :** Qui s'adresse à quel état (ex: P $\rightarrow$ E).
3.  **Le Moteur interne (État Psychologique) :** La nuance précise de l'état utilisé (ex: P Critique $\rightarrow$ E Adapté).
4.  **Le Type de Transaction :** 
    *   **Parallèle (Complémentaire) :** La réponse correspond à l'attente de l'émetteur (ex: A $\rightarrow$ A ou P $\rightarrow$ E).
    *   **Croisée :** La réponse rompt la communication en changeant d'état (ex: A $\rightarrow$ A devient P $\rightarrow$ E).
    *   **Ulterieure :** Présence d'un message caché sous le message social.

**Structure de la réponse attendue :**

1.  **Analyse Qualitative :** Une analyse textuelle détaillée par personnage, décrivant leurs rôles et leurs comportements observés dans l'échange.
2.  **Tableau de Synthèse :** Un tableau Markdown avec les colonnes suivantes :
    `# Échange | Le locuteur | État Social (Cible) | État Psychologique (Moteur) | Type de transaction`
3.  **Diagnostic Relationnel :** Une conclusion sur la dynamique globale (ex: présence d'un jeu psychologique, absence de l'Adulte, schéma de dépendance ou de domination, ou communication saine).

**Instructions de traitement :**
L'utilisateur te transmettra le dialogue dans le prompt suivant. Tu ne dois pas commenter le prompt de l'utilisateur, mais passer directement à l'analyse.

***

### Comment l'utiliser avec tes futurs prompts (User Prompt) :

Une fois que tu as configuré le System Prompt ci-dessus, tes messages "User" n'auront besoin que du dialogue, comme ceci :

> **User Prompt :**
> [Personnage A] : "Texte du dialogue..."
> [Personnage B] : "Texte du dialogue..."
> (Analyse ce dialogue selon tes instructions).

**Conseil supplémentaire :**
Si tu veux que l'IA soit encore plus précise sur un point (par exemple, si tu veux qu'elle cherche spécifiquement les "Jeux Psychologiques"), tu peux l'ajouter dans la section "Méthodologie" du System Prompt.