# VoiceChat Application

This repository contains the VoiceChat application, a real-time communication platform. It features a modern, responsive frontend built with cutting-edge web technologies and a robust Python-based backend for handling voice data and connections.

## Project Structure

The project is organized into two main parts:

-   `VoiceChat/`: Contains the backend logic and client-side Python scripts.
    -   `client/client.py`: Example Python client for interaction.
    -   -   `front/`: The React.js frontend application.
    -   `server/server.py`: Contains the server-side Python implementation.

## Frontend

The frontend for this application is based on the [TelwareSW/telware-frontend](https://github.com/TelwareSW/telware-frontend) project. It has been significantly modified and integrated to serve the specific needs of the VoiceChat application.

**Key Technologies:**
-   **React.js:** A JavaScript library for building user interfaces.
-   **Vite:** A next-generation frontend tooling that provides an extremely fast development experience.
-   **TypeScript:** A typed superset of JavaScript that compiles to plain JavaScript.
-   **Redux Toolkit:** The official, opinionated, batteries-included toolset for efficient Redux development.
-   **Styled-components:** A CSS-in-JS library for styling React components.

### Frontend Setup and Run

1.  Navigate to the frontend directory:
    ```bash
    cd telware-frontend-main/app
    ```
2.  Install dependencies:
    ```bash
    npm install
    ```
3.  Run the development server:
    ```bash
    npm run dev
    ```
    The frontend application will be available in your browser, typically at `http://localhost:5173`.

## Backend

The backend of the VoiceChat application is developed using Python. It handles the core logic for managing real-time voice communication, including peer-to-peer (P2P) and client-server connections.

### Backend Setup and Run (Example for `client.py`)

1.  Navigate to the backend directory:
    ```bash
    cd VoiceChat/client
    ```
2.  Run the Python client (assuming Python and necessary libraries are installed):
    ```bash
    python client.py
    ```

## Features

-   Real-time voice communication
-   Configurable connection modes (P2P Local, P2P Internet, P2P Bluetooth, Client-Server)
-   Customizable audio settings (microphone, headphones, volume control)
-   Language selection (English, Russian)
-   Theme toggling (Light/Dark mode)
-   Modern and responsive UI

## Modifications

This project has been customized and enhanced from the original `telware-frontend` repository. Key modifications include:
-   Integration with a Python backend (Right now its NOT integrated).
-   New "General Settings" section with sub-sections for Language, Appearance, Mode, and Audio.
-   Improved UI/UX for selection components (e.g., custom radio buttons for language and mode selection).
-   Resolution of theming and font display issues across different modes.
-   Addition of headphone selection in audio settings.

## Future Enhancements

-   Implementing actual audio streaming and connection logic for the various modes.
-   Expanding "Storage and Data" settings.
-   User authentication and authorization.
-   Integration of video communication.
-   Persistent settings storage.
