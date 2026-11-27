/*
 *************************************************************************
 * The contents of this file are subject to the Etendo License
 * (the "License"), you may not use this file except in compliance with
 * the License.
 * You may obtain a copy of the License at
 * https://github.com/etendosoftware/etendo_core/blob/main/legal/Etendo_license.txt
 * Software distributed under the License is distributed on an
 * "AS IS" basis, WITHOUT WARRANTY OF ANY KIND, either express or
 * implied. See the License for the specific language governing rights
 * and limitations under the License.
 * All portions are Copyright (C) 2026 FUTIT SERVICES, S.L
 * All Rights Reserved.
 * Contributor(s): Futit Services S.L.
 *************************************************************************
 */
package org.openbravo.database;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.sql.Connection;
import java.sql.SQLException;

import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.mockito.InOrder;

/** Unit tests for the connection handling of {@link SessionInfo}. */
public class SessionInfoTest {

  private Connection originalConnection;

  /** Saves the connection bound to the thread before the test. */
  @Before
  public void saveOriginalConnection() {
    originalConnection = SessionInfo.getSessionConnection();
  }

  /** Restores the connection that was bound to the thread before the test. */
  @After
  public void cleanUp() {
    SessionInfo.setSessionConnection(null);
    SessionInfo.init();
    SessionInfo.setSessionConnection(originalConnection);
  }

  private Connection bind(Connection conn) {
    SessionInfo.setSessionConnection(conn);
    return conn;
  }

  /** close() must run even if setAutoCommit fails. */
  @Test
  public void initClosesConnectionWhenSetAutoCommitFails() throws SQLException {
    Connection conn = bind(mock(Connection.class));
    doThrow(new SQLException("I/O error")).when(conn).setAutoCommit(true);
    SessionInfo.init();
    verify(conn).close();
    assertNull(SessionInfo.getSessionConnection());
  }

  /** A failing close is not propagated and the ThreadLocal is cleared. */
  @Test
  public void initClearsThreadLocalWhenCloseFails() throws SQLException {
    Connection conn = bind(mock(Connection.class));
    doThrow(new SQLException("boom")).when(conn).close();
    SessionInfo.init();
    verify(conn).close();
    assertNull(SessionInfo.getSessionConnection());
  }

  /** Normal case: setAutoCommit(true) and then close(). */
  @Test
  public void initHealthyConnectionSetsAutoCommitThenCloses() throws SQLException {
    Connection conn = bind(mock(Connection.class));
    SessionInfo.init();
    InOrder order = inOrder(conn);
    order.verify(conn).setAutoCommit(true);
    order.verify(conn).close();
    assertNull(SessionInfo.getSessionConnection());
  }

  /** An already closed connection is not touched. */
  @Test
  public void initAlreadyClosedConnectionSkipsSetAutoCommit() throws SQLException {
    Connection conn = bind(mock(Connection.class));
    when(conn.isClosed()).thenReturn(true);
    SessionInfo.init();
    verify(conn, never()).setAutoCommit(true);
    verify(conn, never()).close();
    assertNull(SessionInfo.getSessionConnection());
  }

  /** If isClosed fails the connection is considered broken but close is still attempted. */
  @Test
  public void initClosesConnectionWhenIsClosedFails() throws SQLException {
    Connection conn = bind(mock(Connection.class));
    when(conn.isClosed()).thenThrow(new SQLException("broken"));
    SessionInfo.init();
    verify(conn).close();
    assertNull(SessionInfo.getSessionConnection());
  }

  /** init without bound connection does nothing. */
  @Test
  public void initWithoutConnectionIsNullSafe() {
    SessionInfo.setSessionConnection(null);
    SessionInfo.init();
    assertNull(SessionInfo.getSessionConnection());
  }

  /** An invalid connection is closed and unbound, other thread info is kept. */
  @Test
  public void discardIfInvalidClosesAndUnbindsInvalidConnection() throws SQLException {
    Connection conn = bind(mock(Connection.class));
    when(conn.isValid(5)).thenReturn(false);
    SessionInfo.setUserId("100");
    assertTrue(SessionInfo.discardSessionConnectionIfInvalid(5));
    verify(conn).close();
    assertNull(SessionInfo.getSessionConnection());
    assertEquals("100", SessionInfo.getUserId());
  }

  /** A valid connection is kept. */
  @Test
  public void discardIfInvalidKeepsValidConnection() throws SQLException {
    Connection conn = bind(mock(Connection.class));
    when(conn.isValid(5)).thenReturn(true);
    assertFalse(SessionInfo.discardSessionConnectionIfInvalid(5));
    verify(conn, never()).close();
    assertEquals(conn, SessionInfo.getSessionConnection());
  }

  /** An exception while validating means the connection is discarded. */
  @Test
  public void discardIfInvalidTreatsSQLExceptionAsInvalid() throws SQLException {
    Connection conn = bind(mock(Connection.class));
    when(conn.isValid(5)).thenThrow(new SQLException("broken"));
    assertTrue(SessionInfo.discardSessionConnectionIfInvalid(5));
    verify(conn).close();
    assertNull(SessionInfo.getSessionConnection());
  }

  /** Discarding the connection marks the context as changed so the new connection gets it. */
  @Test
  public void discardMarksContextAsChanged() throws Exception {
    java.lang.reflect.Field field = SessionInfo.class.getDeclaredField("changedInfo");
    field.setAccessible(true);
    @SuppressWarnings("unchecked")
    ThreadLocal<Boolean> changedInfo = (ThreadLocal<Boolean>) field.get(null);
    bind(mock(Connection.class));
    changedInfo.set(false);
    SessionInfo.discardSessionConnection();
    assertEquals(Boolean.TRUE, changedInfo.get());
  }

  /** The invalid-connection discard also marks the context as changed. */
  @Test
  public void discardIfInvalidMarksContextAsChanged() throws Exception {
    java.lang.reflect.Field field = SessionInfo.class.getDeclaredField("changedInfo");
    field.setAccessible(true);
    @SuppressWarnings("unchecked")
    ThreadLocal<Boolean> changedInfo = (ThreadLocal<Boolean>) field.get(null);
    Connection conn = bind(mock(Connection.class));
    when(conn.isValid(5)).thenReturn(false);
    changedInfo.set(false);
    assertTrue(SessionInfo.discardSessionConnectionIfInvalid(5));
    assertEquals(Boolean.TRUE, changedInfo.get());
  }

  /** init() keeps resetting changedInfo to null. */
  @Test
  public void initResetsChangedInfo() throws Exception {
    java.lang.reflect.Field field = SessionInfo.class.getDeclaredField("changedInfo");
    field.setAccessible(true);
    @SuppressWarnings("unchecked")
    ThreadLocal<Boolean> changedInfo = (ThreadLocal<Boolean>) field.get(null);
    bind(mock(Connection.class));
    changedInfo.set(true);
    SessionInfo.init();
    assertNull(changedInfo.get());
  }
}
