package org.openbravo.test.ci;

import org.junit.platform.suite.api.SelectClasses;
import org.junit.platform.suite.api.Suite;

@Suite
@SelectClasses({
    com.etendoerp.advpaymentmngt.actionHandler.PaymentExecutionProcessActionHandlerTest.class,
    com.etendoerp.email.spi.DefaultSmtpEmailSenderTest.class,
    com.etendoerp.email.spi.EmailSendContextTest.class,
    com.etendoerp.email.spi.EmailSenderDispatcherTest.class,
    com.etendoerp.format.mask.MaskFormatterTest.class,
    com.etendoerp.sequences.DefaultSequenceGeneratorTest.class,
    com.etendoerp.sequences.SequencesGeneratorTest.class,
    com.etendoerp.sequences.dimensions.ASequenceDimensionListOBTest.class,
    com.etendoerp.sequences.dimensions.DimensionListOriginalColumnFormatTest.class,
    com.etendoerp.sequences.dimensions.DimensionListRequestParameterFormatTest.class,
    com.etendoerp.sequences.dimensions.LoadDimensionsMapTest.class,
    com.etendoerp.sequences.dimensions.SequenceDimensionTest.class,
    com.etendoerp.sequences.transactional.BusinessPartnerSequenceGenerationRecursionTest.class,
    com.etendoerp.sequences.transactional.DefaultTransactionalSequencePreloadRaceTest.class,
    com.etendoerp.sequences.transactional.TransactionalSequenceUpdateNextTest.class,
    com.etendoerp.sequences.transactional.TransactionalSequenceUtilsTest.class,
})
public class CoreEtendoerpTestSuite {
}
