import streamlit as st
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from hashlib import sha256
import sqlite3
import requests
import os

# Connect to the database
conn = sqlite3.connect('books_library.db')
c = conn.cursor()

# Create tables if they don't exist
c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE,
        email TEXT UNIQUE,
        password TEXT
    )
''')
c.execute('''
    CREATE TABLE IF NOT EXISTS books (
        id INTEGER PRIMARY KEY,
        title TEXT,
        author TEXT,
        genre TEXT,
        pdf_link TEXT
    )
''')
conn.commit()

# Load book data
books_df = pd.read_csv('books.csv')
books_new_df = pd.read_csv('books_new.csv')
books_df = pd.concat([books_df, books_new_df], ignore_index=True)

# Remove leading/trailing whitespace from column names
books_df.columns = books_df.columns.str.strip()

# Verify if the required columns exist
required_columns = ['Title', 'Author', 'Genre']
for col in required_columns:
    if col not in books_df.columns:
        st.error(f"The column '{col}' does not exist in the book data.")
        break
else:
    def recommend_books(selected_book_title, books_df, num_recommendations=5):
        selected_book = books_df[books_df['Title'] == selected_book_title].iloc[0]
        selected_genre = selected_book['Genre']
        recommendations = books_df[books_df['Genre'] == selected_genre]
        recommendations = recommendations[recommendations['Title'] != selected_book_title]
        return recommendations.head(num_recommendations)

    def get_user_ratings_matrix(ratings_df):
        user_ratings_matrix = ratings_df.pivot(index='user_id', columns='book_title', values='rating').fillna(0)
        return user_ratings_matrix

    def recommend_books_collaborative(user_ratings_matrix, user_id, num_recommendations=5):
        user_similarity = cosine_similarity(user_ratings_matrix)
        user_similarity_df = pd.DataFrame(user_similarity, index=user_ratings_matrix.index, columns=user_ratings_matrix.index)
        similar_users = user_similarity_df[user_id].sort_values(ascending=False).index[1:]
        similar_users_ratings = user_ratings_matrix.loc[similar_users].mean(axis=0)
        recommendations = similar_users_ratings.sort_values(ascending=False)
        return recommendations.head(num_recommendations)

    def hybrid_recommendations(selected_book_title, user_id, books_df, ratings_df, num_recommendations=5):
        content_recs = recommend_books(selected_book_title, books_df, num_recommendations)
        user_ratings_matrix = get_user_ratings_matrix(ratings_df)
        collaborative_recs = recommend_books_collaborative(user_ratings_matrix, user_id, num_recommendations)
        combined_recs = pd.concat([content_recs, collaborative_recs], axis=0).drop_duplicates().reset_index(drop=True)
        return combined_recs.head(num_recommendations)

    def get_online_recommendations(query, num_recommendations=2):
        api_key = 'AIzaSyB_i-Ndi7er4dmWhV75glOCY1Ch465Bcfc'
        search_url = f"https://www.googleapis.com/books/v1/volumes?q={query}&key={api_key}"
        response = requests.get(search_url)
        books = response.json().get('items', [])

        recommendations = []
        for book in books[:num_recommendations]:
            title = book['volumeInfo'].get('title', 'No Title')
            author = ', '.join(book['volumeInfo'].get('authors', ['No Author']))
            pdf_link = book['volumeInfo'].get('previewLink', '')
            recommendations.append({'Title': title, 'Author': author, 'PDF Link': pdf_link})
        
        return pd.DataFrame(recommendations)

    def handle_file_upload(uploaded_file, book_title, book_author, book_genre):
        if uploaded_file is not None:
            save_path = os.path.join('uploaded_books', uploaded_file.name)
            with open(save_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            # Save the book details in the database
            c.execute('''
                INSERT INTO books (title, author, genre, pdf_link)
                VALUES (?, ?, ?, ?)
            ''', (book_title, book_author, book_genre, save_path))
            conn.commit()
            st.success("Book uploaded successfully!")

    def handle_file_download(book_pdf_link):
        st.markdown(f"[Download Book]({book_pdf_link})", unsafe_allow_html=True)

    def book_library_page():
        st.title("Book Library")
        
        # Directory to save uploaded books
        upload_dir = 'uploaded_books'
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir)

        # Upload Book Section
        st.subheader("Upload Book")
        uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")
        book_title = st.text_input("Enter the title of the book")
        book_author = st.text_input("Enter the author of the book")
        book_genre = st.text_input("Enter the genre of the book")
        
        if st.button('Upload Book'):
            if book_title and book_author and book_genre:
                handle_file_upload(uploaded_file, book_title, book_author, book_genre)
            else:
                st.error("Please fill in all the fields.")

        # Display Uploaded Books Section
        st.subheader("Available Books")
        c.execute("SELECT title, author, genre, pdf_link FROM books")
        uploaded_books = c.fetchall()
        
        for book in uploaded_books:
            st.write(f"**Title:** {book[0]}")
            st.write(f"**Author:** {book[1]}")
            st.write(f"**Genre:** {book[2]}")
            handle_file_download(book[3])
            st.write("---")

    def book_search_page():
        st.title("Book Search")
        query = st.text_input("Search for a book by title or author")
        if st.button("Search"):
            # Search in local database
            c.execute("SELECT title, author, genre, pdf_link FROM books WHERE title LIKE ?", ('%' + query + '%',))
            local_results = c.fetchall()

            if local_results:
                st.write("Local Search Results:")
                for book in local_results:
                    st.write(f"**Title:** {book[0]}")
                    st.write(f"**Author:** {book[1]}")
                    st.write(f"**Genre:** {book[2]}")
                    handle_file_download(book[3])
                    st.write("---")
            else:
                st.write("No books found in the local database.")

            # Search online
            online_results = get_online_recommendations(query)
            if not online_results.empty:
                st.write("Online Search Results:")
                for index, row in online_results.iterrows():
                    st.write(f"**Title:** {row['Title']}")
                    st.write(f"**Author:** {row['Author']}")
                    if row['PDF Link']:
                        st.markdown(f"[Download Book]({row['PDF Link']})", unsafe_allow_html=True)
                    else:
                        st.write("No PDF available")
                    st.write("---")
            else:
                st.write("No books found online.")

    # Streamlit App
    st.title('Book Recommendation System')

    # Sidebar for registration, login, and logout
    with st.sidebar:
        if 'user' in st.session_state:
            st.subheader('User Menu')
            st.write(f"Welcome, {st.session_state['username']}")
            if st.button('Logout'):
                del st.session_state['user']
                del st.session_state['username']
                st.success('Logged out successfully!')
        else:
            st.subheader('Login/Register')
            choice = st.radio("Choose an option", ["Login", "Register"])

            if choice == "Register":
                st.subheader('Register')
                username = st.text_input('Username')
                email = st.text_input('Email')
                password = st.text_input('Password', type='password')

                if st.button('Register'):
                    hashed_password = sha256(password.encode()).hexdigest()
                    try:
                        c.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)', (username, email, hashed_password))
                        conn.commit()
                        st.success('Registration successful!')
                    except sqlite3.IntegrityError:
                        st.error('Username or email already exists')

            elif choice == "Login":
                st.subheader('Login')
                username = st.text_input('Username')
                password = st.text_input('Password', type='password')

                if st.button('Login'):
                    hashed_password = sha256(password.encode()).hexdigest()
                    c.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, hashed_password))
                    user = c.fetchone()
                    if user:
                        st.session_state['user'] = user[0]
                        st.session_state['username'] = username
                        st.success('Login successful!')
                    else:
                        st.error('Invalid credentials')

    # Main app content
    if 'user' in st.session_state:
        page = st.sidebar.selectbox("Select Page", ["Book Recommendations", "Book Library", "Book Search"])

        if page == "Book Recommendations":
            st.subheader('Book Search and Recommendations')
            if 'Title' in books_df.columns:
                selected_book_title = st.selectbox('Select a book', books_df['Title'].unique())
                num_recommendations = st.slider('Number of recommendations', 1, 10, 5)
                recommendations = recommend_books(selected_book_title, books_df, num_recommendations)
                st.write('Recommendations based on content:')
                st.write(recommendations)
                
                st.write('Recommendations based on collaborative filtering:')
                user_ratings_df = pd.read_csv('user_ratings.csv')  # Assume this file exists
                collaborative_recs = recommend_books_collaborative(get_user_ratings_matrix(user_ratings_df), st.session_state['user'], num_recommendations)
                st.write(collaborative_recs)
                
                st.write('Hybrid Recommendations:')
                hybrid_recs = hybrid_recommendations(selected_book_title, st.session_state['user'], books_df, user_ratings_df, num_recommendations)
                st.write(hybrid_recs)
            else:
                st.error('The "Title" column is missing in the book data.')
                
        elif page == "Book Library":
            book_library_page()
        
        elif page == "Book Search":
            book_search_page()
